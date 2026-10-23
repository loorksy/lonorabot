"""Attention-backed invitations reuse durable voice rows, events and receipts.

No microphone, provider session, task or financial grant is created by an invitation.
Delivery adapters must honor their idempotency key across ambiguous network outcomes.
"""

from datetime import datetime, timedelta
from typing import Any, Protocol

from lonora_contracts.domain import utcnow
from lonora_contracts.incoming_calls import IncomingCallPolicy
from lonora_core.user_error import LonoraError
from lonora_db.attention import mandatory_current
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.schema import AttentionRow, DeviceCredentialRow, VoiceSessionRow
from lonora_db.transactions import SettingsRepository, owned_agent, owned_thread
from lonora_session.idempotency import stable_id
from sqlalchemy import and_, or_, select, text
from sqlalchemy.ext.asyncio import AsyncSession

MODE = "incoming_request"
ACTIVE = {"ringing"}


class IncomingDelivery(Protocol):
    """Authenticated native push/OS delivery, not an Agent or execution runtime."""

    async def send(
        self,
        *,
        owner_id: str,
        device_id: str,
        call_id: str,
        expires_at: datetime,
        idempotency_key: str,
    ) -> None: ...


def call_data(row: VoiceSessionRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "thread_id": row.thread_id,
        "status": row.payload["status"],
        "reason": row.payload["reason"],
        "attention_id": row.payload["attention_id"],
        "expires_at": row.payload["expires_at"],
        "version": row.version,
        "execution_authorized": False,
    }


async def owner_lock(session: AsyncSession, owner_id: str) -> None:
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "incoming-call:" + owner_id},
        )


async def preferences(session: AsyncSession, owner_id: str) -> IncomingCallPolicy:
    return IncomingCallPolicy.model_validate(
        await SettingsRepository().get(session, "incoming-call-policy:" + owner_id)
    )


async def verified_device(session: AsyncSession, owner_id: str, device_id: str) -> None:
    device = await session.get(DeviceCredentialRow, device_id)
    if device is None or device.owner_id != owner_id or device.revoked:
        raise LonoraError("incoming_call_device_unavailable", 403)


async def set_preferences(session: AsyncSession, owner_id: str, policy: IncomingCallPolicy) -> None:
    await owner_lock(session, owner_id)
    if policy.enabled:
        await verified_device(session, owner_id, policy.device_id or "")
    await SettingsRepository().put(
        session, "incoming-call-policy:" + owner_id, policy.model_dump(mode="json")
    )


def changed(session: AsyncSession, row: VoiceSessionRow, status: str) -> None:
    row.payload = {**row.payload, "status": status}
    row.version += 1
    row.updated_at = utcnow()
    emit(
        session,
        row.owner_id,
        "voice.incoming.updated",
        agent_id=row.agent_id,
        thread_id=row.thread_id,
        payload=call_data(row),
    )


async def current_attention(session: AsyncSession, row: VoiceSessionRow) -> AttentionRow:
    source = await session.get(AttentionRow, row.payload["attention_id"])
    if source is None or source.owner_id != row.owner_id or source.status != "ready":
        raise LonoraError("incoming_call_attention_unavailable", 409)
    if source.agent_id != row.agent_id or source.thread_id != row.thread_id:
        raise LonoraError("incoming_call_scope_mismatch", 403)
    deadline = source.parameters.get("valid_until")
    if deadline and datetime.fromisoformat(deadline) <= utcnow():
        raise LonoraError("incoming_call_attention_expired", 409)
    if source.importance in {"critical", "action_required"} and not await mandatory_current(
        session, source
    ):
        raise LonoraError("incoming_call_attention_superseded", 409)
    return source


async def require_current_consent(session: AsyncSession, row: VoiceSessionRow) -> None:
    policy = await preferences(session, row.owner_id)
    if not policy.enabled or policy.device_id != row.payload["device_id"]:
        raise LonoraError("incoming_calls_disabled", 409)
    await verified_device(session, row.owner_id, row.payload["device_id"])
    source = await current_attention(session, row)
    if not {
        "critical": policy.critical,
        "action_required": policy.action_required,
        "opportunity": policy.opportunities,
    }.get(source.importance, False):
        raise LonoraError("incoming_call_category_disabled", 409)
    if policy.quiet(utcnow()):
        raise LonoraError("incoming_call_quiet_hours", 409)
    agent = await owned_agent(session, row.owner_id, row.agent_id or "")
    thread = await owned_thread(session, row.owner_id, row.thread_id or "")
    if agent.paused or thread.agent_id != agent.id:
        raise LonoraError("incoming_call_scope_unavailable", 409)


async def request_call(
    session: AsyncSession,
    owner_id: str,
    attention_id: str,
    reason: str,
    *,
    agent_id: str | None = None,
    thread_id: str | None = None,
) -> VoiceSessionRow:
    await owner_lock(session, owner_id)
    identifier = stable_id(owner_id, "incoming-call:" + attention_id)
    previous = await session.get(VoiceSessionRow, identifier)
    if previous is not None:
        if (agent_id and previous.agent_id != agent_id) or (
            thread_id and previous.thread_id != thread_id
        ):
            raise LonoraError("incoming_call_scope_mismatch", 403)
        return previous
    policy = await preferences(session, owner_id)
    if not policy.enabled:
        raise LonoraError("incoming_calls_disabled", 409)
    await verified_device(session, owner_id, policy.device_id or "")
    source = await session.get(AttentionRow, attention_id)
    if source is None or source.owner_id != owner_id or source.status != "ready":
        raise LonoraError("incoming_call_attention_unavailable", 404)
    if (agent_id and source.agent_id != agent_id) or (thread_id and source.thread_id != thread_id):
        raise LonoraError("incoming_call_scope_mismatch", 403)
    allowed = {
        "critical": policy.critical,
        "action_required": policy.action_required,
        "opportunity": policy.opportunities,
    }
    if not allowed.get(source.importance, False):
        raise LonoraError("incoming_call_category_disabled", 409)
    now = utcnow()
    if policy.quiet(now):
        raise LonoraError("incoming_call_quiet_hours", 409)
    agent = await owned_agent(session, owner_id, source.agent_id)
    thread = await owned_thread(session, owner_id, source.thread_id)
    if agent.paused or thread.agent_id != agent.id:
        raise LonoraError("incoming_call_scope_unavailable", 409)
    rows = list(
        await session.scalars(
            select(VoiceSessionRow)
            .where(
                VoiceSessionRow.owner_id == owner_id,
                or_(
                    and_(
                        VoiceSessionRow.payload["mode"].as_string() == MODE,
                        or_(
                            VoiceSessionRow.payload["status"].as_string() == "ringing",
                            VoiceSessionRow.created_at
                            > now - timedelta(seconds=policy.minimum_interval_seconds),
                        ),
                    ),
                    and_(
                        VoiceSessionRow.payload["mode"].as_string() == "gpt_live",
                        VoiceSessionRow.payload["status"]
                        .as_string()
                        .in_(["allocating", "joining", "connected", "closing"]),
                    ),
                ),
            )
            .with_for_update()
        )
    )
    for row in rows:
        if row.payload.get("mode") == MODE and row.payload.get("status") in ACTIVE:
            if datetime.fromisoformat(row.payload["expires_at"]) <= now:
                changed(session, row, "missed")
            else:
                raise LonoraError("incoming_call_already_active", 409)
        elif row.payload.get("mode") == "gpt_live" and row.payload.get("status") in {
            "allocating",
            "joining",
            "connected",
            "closing",
        }:
            raise LonoraError("incoming_call_already_active", 409)
        if row.payload.get("mode") == MODE and row.created_at > now - timedelta(
            seconds=policy.minimum_interval_seconds
        ):
            raise LonoraError("incoming_call_rate_limited", 429)
    expires = now + timedelta(seconds=policy.ttl_seconds)
    if source.parameters.get("valid_until"):
        expires = min(expires, datetime.fromisoformat(source.parameters["valid_until"]))
    row = VoiceSessionRow(
        id=identifier,
        owner_id=owner_id,
        agent_id=agent.id,
        thread_id=thread.id,
        payload={
            "mode": MODE,
            "status": "ringing",
            "attention_id": source.id,
            "reason": reason,
            "device_id": policy.device_id,
            "expires_at": expires.isoformat(),
        },
        state={"delivery": "provider_unconfigured"},
        version=1,
    )
    await current_attention(session, row)
    session.add(row)
    await session.flush()
    emit(
        session,
        owner_id,
        "voice.incoming.updated",
        agent_id=row.agent_id,
        thread_id=row.thread_id,
        payload=call_data(row),
    )
    return row


async def owned_call(session: AsyncSession, owner_id: str, identifier: str) -> VoiceSessionRow:
    row = await session.get(VoiceSessionRow, identifier, with_for_update=True)
    if row is None or row.owner_id != owner_id or row.payload.get("mode") != MODE:
        raise LonoraError("incoming_call_not_found", 404)
    return row


async def transition(
    session: AsyncSession, owner_id: str, identifier: str, action: str, device_id: str
) -> VoiceSessionRow:
    await owner_lock(session, owner_id)
    row = await owned_call(session, owner_id, identifier)
    await verified_device(session, owner_id, device_id)
    if row.payload["device_id"] != device_id:
        raise LonoraError("incoming_call_device_mismatch", 403)
    if row.payload["status"] not in ACTIVE:
        return row
    if datetime.fromisoformat(row.payload["expires_at"]) <= utcnow():
        changed(session, row, "missed")
        return row
    if action == "accept":
        await require_current_consent(session, row)
        if row.payload["status"] == "ringing":
            changed(session, row, "accepted")
    elif action in {"reject", "cancel"}:
        changed(session, row, "rejected" if action == "reject" else "cancelled")
    else:
        raise LonoraError("incoming_call_action_invalid", 422)
    return row


async def incoming_tick(
    db: Database, owner_id: str, delivery: IncomingDelivery | None = None
) -> int:
    """Resident Gateway maintenance; safe to replay after a process restart."""
    delivered = 0
    async with db.sessions() as session:
        identifiers = list(
            await session.scalars(
                select(VoiceSessionRow.id).where(
                    VoiceSessionRow.owner_id == owner_id,
                    VoiceSessionRow.payload["mode"].as_string() == MODE,
                    VoiceSessionRow.payload["status"].as_string().in_(list(ACTIVE)),
                )
            )
        )
    for identifier in identifiers:
        async with db.sessions() as session, session.begin():
            await owner_lock(session, owner_id)
            row = await owned_call(session, owner_id, identifier)
            if row.payload["status"] not in ACTIVE:
                continue
            now = utcnow()
            if datetime.fromisoformat(row.payload["expires_at"]) <= now:
                changed(session, row, "missed")
                continue
            try:
                await require_current_consent(session, row)
            except LonoraError:
                changed(session, row, "cancelled")
                continue
            if row.payload["status"] != "ringing" or row.state.get("delivery") == "delivered":
                continue
            if delivery is None:
                row.state = {**row.state, "delivery": "provider_unconfigured"}
                continue
            retry_at = row.state.get("retry_at")
            if retry_at and datetime.fromisoformat(retry_at) > now:
                continue
            # Bounded provider IO under the owner lock serializes dispatch with
            # rejection/revocation. Provider MUST durably honor this stable key.
            import asyncio

            try:
                async with asyncio.timeout(5):
                    await delivery.send(
                        owner_id=owner_id,
                        device_id=row.payload["device_id"],
                        call_id=row.id,
                        expires_at=datetime.fromisoformat(row.payload["expires_at"]),
                        idempotency_key="incoming-call:" + row.id,
                    )
            except Exception:
                attempt = int(row.state.get("attempt", 0)) + 1
                row.state = {
                    **row.state,
                    "delivery": "retry_pending",
                    "attempt": attempt,
                    "retry_at": (
                        now + timedelta(seconds=min(30, 2 ** min(attempt, 5)))
                    ).isoformat(),
                }
            else:
                row.state = {**row.state, "delivery": "delivered"}
                delivered += 1
    return delivered
