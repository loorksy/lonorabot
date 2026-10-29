"""One per-Agent approval preference over existing signed financial authority.

This is not an authorization engine: autonomous scope is always read from valid
AccountAuthority records. Stored preferences/drafts cannot activate a grant.
"""

from hashlib import sha256
from typing import Any

from lonora_contracts.agent_permissions import (
    PermissionChange,
    PermissionCustomizationChange,
    PermissionLevel,
    PermissionRecord,
    PermissionStatus,
)
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import AccountAuthorityRow, SettingRow, SuperBotRequestRow
from .super_bot import authority_lock, stop_request
from .transactions import owned_agent


def permission_key(owner_id: str, agent_id: str) -> str:
    return "agent-permission:" + sha256((owner_id + ":" + agent_id).encode()).hexdigest()


async def permission_record(
    session: AsyncSession, owner_id: str, agent_id: str
) -> PermissionRecord:
    await owned_agent(session, owner_id, agent_id)
    row = await session.get(SettingRow, permission_key(owner_id, agent_id), populate_existing=True)
    try:
        value = (
            PermissionRecord.model_validate(row.payload)
            if row
            else PermissionRecord(owner_id=owner_id, agent_id=agent_id)
        )
    except ValidationError:
        raise LonoraError("agent_permission_state_invalid", 409) from None
    if value.owner_id != owner_id or value.agent_id != agent_id:
        raise LonoraError("agent_permission_scope_mismatch", 409)
    return value


async def _write(session: AsyncSession, record: PermissionRecord) -> None:
    key = permission_key(record.owner_id, record.agent_id)
    row = await session.get(SettingRow, key, populate_existing=True)
    payload = record.model_dump(mode="json")
    if row is None:
        session.add(SettingRow(key=key, payload=payload))
    else:
        row.payload = payload
        row.updated_at = utcnow()
    await session.flush()
    emit(
        session,
        record.owner_id,
        "agent.permission.updated",
        agent_id=record.agent_id,
        payload={"agent_id": record.agent_id, "revision": record.revision},
    )


async def bump_permission(session: AsyncSession, owner_id: str, agent_id: str) -> None:
    """Caller holds authority_lock; envelope creation/activation/revocation changed."""
    current = await permission_record(session, owner_id, agent_id)
    await _write(session, current.model_copy(update={"revision": current.revision + 1}))


async def assert_permission_revision(
    session: AsyncSession, owner_id: str, agent_id: str, expected: int | None
) -> None:
    if (
        expected is not None
        and (await permission_record(session, owner_id, agent_id)).revision != expected
    ):
        raise LonoraError("version_conflict", 409)


async def _active_authorities(
    session: AsyncSession, owner_id: str, agent_id: str
) -> list[AccountAuthorityRow]:
    from .account_authority import require_authority

    rows = list(
        await session.scalars(
            select(AccountAuthorityRow)
            .where(
                AccountAuthorityRow.owner_id == owner_id,
                AccountAuthorityRow.agent_id == agent_id,
                AccountAuthorityRow.status == "active",
            )
            .order_by(AccountAuthorityRow.created_at.desc())
            .execution_options(populate_existing=True)
        )
    )
    result: list[AccountAuthorityRow] = []
    for row in rows:
        try:
            await require_authority(session, owner_id, agent_id, row.id)
        except LonoraError:
            continue
        result.append(row)
    return result


async def effective_permission(
    session: AsyncSession, owner_id: str, agent_id: str
) -> PermissionLevel:
    record = await permission_record(session, owner_id, agent_id)
    return (
        "autonomous"
        if await _active_authorities(session, owner_id, agent_id)
        else record.fallback_level
    )


async def permission_state(session: AsyncSession, owner_id: str, agent_id: str) -> dict[str, Any]:
    from .account_authority import authority_data

    record = await permission_record(session, owner_id, agent_id)
    active = await _active_authorities(session, owner_id, agent_id)
    recent = list(
        await session.scalars(
            select(AccountAuthorityRow)
            .where(
                AccountAuthorityRow.owner_id == owner_id,
                AccountAuthorityRow.agent_id == agent_id,
            )
            .order_by(AccountAuthorityRow.created_at.desc())
            .limit(20)
            .execution_options(populate_existing=True)
        )
    )
    pending = next((row for row in recent if authority_data(row)["status"] == "pending"), None)
    effective: PermissionLevel = "autonomous" if active else record.fallback_level
    status: PermissionStatus = effective
    if pending:
        status = "awaiting_authorization"
    elif not active and recent:
        latest = authority_data(recent[0])["status"]
        if latest == "expired":
            status = "authorization_expired"
        elif latest == "revoked":
            status = "autonomous_stopped"
    return {
        "agent_id": agent_id,
        "revision": record.revision,
        "effective_level": effective,
        "fallback_level": record.fallback_level,
        "requested_level": "autonomous" if pending else effective,
        "status": status,
        "active_authorities": [authority_data(row) for row in active],
        "pending_authority": authority_data(pending) if pending else None,
        "customization": record.customization.model_dump(mode="json")
        if record.customization
        else None,
    }


async def change_permission(
    session: AsyncSession, owner_id: str, agent_id: str, body: PermissionChange
) -> dict[str, Any]:
    from .account_authority import changed, stop_management_task

    await authority_lock(session, agent_id)
    agent = await owned_agent(session, owner_id, agent_id)
    if agent.role == "delegated" and body.level != "analysis":
        raise LonoraError("delegated_financial_authority_forbidden", 403)
    record = await permission_record(session, owner_id, agent_id)
    await assert_permission_revision(session, owner_id, agent_id, body.expected_revision)
    grants = list(
        await session.scalars(
            select(AccountAuthorityRow)
            .where(
                AccountAuthorityRow.owner_id == owner_id,
                AccountAuthorityRow.agent_id == agent_id,
                AccountAuthorityRow.status.in_(["pending", "active"]),
            )
            .order_by(AccountAuthorityRow.id)
            .with_for_update()
        )
    )
    for row in grants:
        row.status = "revoked"
        await stop_management_task(session, row)
        changed(session, row)
    # Remove only existing financial Goal delegation. Keep the analytical goal,
    # watches and routines, and never send broker close/cancel operations here.
    legacy = list(
        await session.scalars(
            select(SuperBotRequestRow)
            .where(
                SuperBotRequestRow.owner_id == owner_id,
                SuperBotRequestRow.agent_id == agent_id,
                SuperBotRequestRow.status.in_(["pending", "activated"]),
            )
            .order_by(SuperBotRequestRow.goal_id)
        )
    )
    for row in legacy:
        await stop_request(session, row, "disabled")
    await _write(
        session,
        record.model_copy(
            update={
                "fallback_level": body.level,
                "revision": record.revision + 1,
            }
        ),
    )
    return await permission_state(session, owner_id, agent_id)


async def save_customization(
    session: AsyncSession, owner_id: str, agent_id: str, body: PermissionCustomizationChange
) -> dict[str, Any]:
    from .agent_binding import assert_market_binding
    from .broker_sessions import BrokerSessionRepository

    await authority_lock(session, agent_id)
    agent = await owned_agent(session, owner_id, agent_id)
    await assert_permission_revision(session, owner_id, agent_id, body.expected_revision)
    draft = body.customization
    if draft.account_id:
        await BrokerSessionRepository().get(session, owner_id, draft.account_id)
        assert_market_binding(agent, draft.account_id)
    if draft.symbol_scope == "account" and agent.role != "personal":
        raise LonoraError("account_authority_scope_mismatch", 403)
    for symbol in draft.symbols:
        if not symbol or len(symbol) > 80 or symbol != symbol.strip():
            raise LonoraError("authority_exact_symbols_required", 422)
        assert_market_binding(agent, draft.account_id or None, symbol)
    current = await permission_record(session, owner_id, agent_id)
    await _write(
        session,
        current.model_copy(update={"customization": draft, "revision": current.revision + 1}),
    )
    return await permission_state(session, owner_id, agent_id)
