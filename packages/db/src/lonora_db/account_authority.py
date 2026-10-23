"""Durable account authority, never inherited from conversation or Goal state."""

from datetime import timedelta
from typing import Any

from lonora_contracts.account_authority import AccountAuthorityEnvelope, AccountAuthorityProposal
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import request_hash, stable_id
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_binding import assert_market_binding, require_financial_agent
from .broker_sessions import BrokerSessionRepository
from .events import emit
from .schema import AccountAuthorityRow, DeviceCredentialRow, TicketRow
from .super_bot import authority_lock
from .transactions import owned_thread


def authority_data(row: AccountAuthorityRow) -> dict[str, Any]:
    now = utcnow()
    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "thread_id": row.thread_id,
        "account_id": row.account_id,
        "status": "expired"
        if row.status in {"pending", "active"}
        and (
            row.valid_until is not None
            and row.valid_until <= now
            or row.status == "pending"
            and row.activation_expires_at <= now
        )
        else row.status,
        "envelope": row.envelope,
        "activation_expires_at": row.activation_expires_at.isoformat(),
        "valid_until": row.valid_until.isoformat() if row.valid_until else None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "monetary_stop_risk": "unavailable",
    }


def changed(session: AsyncSession, row: AccountAuthorityRow) -> None:
    row.updated_at = utcnow()
    emit(
        session,
        row.owner_id,
        "account_authority.updated",
        agent_id=row.agent_id,
        thread_id=row.thread_id,
        payload=authority_data(row),
    )


async def owned_authority(
    session: AsyncSession, owner_id: str, identifier: str, *, lock: bool = False
) -> AccountAuthorityRow:
    row = await session.get(
        AccountAuthorityRow, identifier, with_for_update=lock, populate_existing=True
    )
    if row is None or row.owner_id != owner_id:
        raise LonoraError("account_authority_not_found", 404)
    return row


async def validate_scope(
    session: AsyncSession, owner_id: str, agent_id: str, envelope: AccountAuthorityEnvelope
) -> None:
    if envelope.owner_id != owner_id or envelope.agent_id != agent_id:
        raise LonoraError("account_authority_scope_changed", 403)
    agent = await require_financial_agent(session, owner_id, agent_id)
    if agent.paused:
        raise LonoraError("agent_paused", 409)
    thread = await owned_thread(session, owner_id, envelope.thread_id)
    if thread.agent_id != agent_id or thread.group_id:
        raise LonoraError("agent_thread_mismatch", 409)
    await BrokerSessionRepository().get(session, owner_id, envelope.account_id)
    if envelope.symbol_scope == "account" and (
        agent.role != "personal" or agent.trading_account_id or agent.trading_symbol
    ):
        raise LonoraError("account_authority_scope_mismatch", 403)
    for symbol in envelope.symbols:
        assert_market_binding(agent, envelope.account_id, symbol)


async def propose(
    session: AsyncSession, owner_id: str, agent_id: str, body: AccountAuthorityProposal
) -> AccountAuthorityRow:
    await authority_lock(session, agent_id)
    if body.valid_until is not None and (
        body.valid_until <= utcnow()
        or body.management_mode == "bounded"
        and body.valid_until > utcnow() + timedelta(days=30)
    ):
        raise LonoraError("account_authority_expiry_invalid", 422)
    envelope = AccountAuthorityEnvelope(
        **body.model_dump(),
        owner_id=owner_id,
        agent_id=agent_id,
        schema_version=2 if body.management_mode == "full" else 1,
    )
    await validate_scope(session, owner_id, agent_id, envelope)
    payload = envelope.model_dump(mode="json")
    digest = request_hash(payload)
    previous = await session.scalar(
        select(AccountAuthorityRow)
        .where(
            AccountAuthorityRow.owner_id == owner_id,
            AccountAuthorityRow.agent_id == agent_id,
            AccountAuthorityRow.envelope_hash == digest,
            AccountAuthorityRow.status == "pending",
            AccountAuthorityRow.activation_expires_at > utcnow(),
        )
        .limit(1)
    )
    if previous:
        return previous
    row = AccountAuthorityRow(
        owner_id=owner_id,
        agent_id=agent_id,
        thread_id=body.thread_id,
        account_id=body.account_id,
        envelope=payload,
        envelope_hash=digest,
        activation_expires_at=utcnow() + timedelta(minutes=10),
        valid_until=body.valid_until,
    )
    session.add(row)
    await session.flush()
    changed(session, row)
    return row


async def require_authority(
    session: AsyncSession, owner_id: str, agent_id: str, identifier: str
) -> tuple[AccountAuthorityRow, AccountAuthorityEnvelope]:
    row = await owned_authority(session, owner_id, identifier)
    if (
        row.agent_id != agent_id
        or row.status != "active"
        or (row.valid_until is not None and row.valid_until <= utcnow())
    ):
        raise LonoraError("account_authority_unavailable", 403)
    if request_hash(row.envelope) != row.envelope_hash:
        raise LonoraError("account_authority_changed", 403)
    try:
        envelope = AccountAuthorityEnvelope.model_validate(row.envelope)
    except ValidationError as error:
        raise LonoraError("account_authority_changed", 403) from error
    if (
        envelope.valid_until != row.valid_until
        or envelope.account_id != row.account_id
        or envelope.thread_id != row.thread_id
    ):
        raise LonoraError("account_authority_changed", 403)
    await validate_scope(session, owner_id, agent_id, envelope)
    device = await session.get(DeviceCredentialRow, row.device_id or "", populate_existing=True)
    if device is None or device.owner_id != owner_id or device.revoked:
        raise LonoraError("device_authorization_required", 403)
    return row, envelope


async def revoke(session: AsyncSession, owner_id: str, identifier: str) -> AccountAuthorityRow:
    candidate = await owned_authority(session, owner_id, identifier)
    await authority_lock(session, candidate.agent_id)
    row = await owned_authority(session, owner_id, identifier, lock=True)
    row.status = "revoked"
    await stop_management_task(session, row)
    changed(session, row)
    return row


async def stop_management_task(session: AsyncSession, row: AccountAuthorityRow) -> None:
    """Stop only this grant's existing Task; preserve all broker journal effects."""
    from .tasks import finish_task

    task = await session.get(
        TicketRow,
        stable_id(row.id, "account-management-task"),
        with_for_update=True,
        populate_existing=True,
    )
    if task and task.owner_id == row.owner_id and task.agent_id == row.agent_id:
        finish_task(session, task, "cancelled")
