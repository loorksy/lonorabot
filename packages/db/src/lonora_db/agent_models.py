"""One owner-chosen model preference per Agent, stored without a schema change.

Like the per-Agent approval preference, the record lives in ``ln_settings``
under an owner-scoped key. It only orders the model candidates the router
tries; it never grants authority or changes what the Agent may do.
"""

from hashlib import sha256

from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import (
    AgentModelChange,
    AgentModelPreference,
    AgentModelRecord,
)
from lonora_core.user_error import LonoraError
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import SettingRow
from .transactions import owned_agent


def agent_model_key(owner_id: str, agent_id: str) -> str:
    return "agent-model:" + sha256((owner_id + ":" + agent_id).encode()).hexdigest()


async def stored_agent_model(
    session: AsyncSession, owner_id: str, agent_id: str
) -> AgentModelRecord:
    """The record for an Agent the caller already scoped; empty when unset."""
    row = await session.get(SettingRow, agent_model_key(owner_id, agent_id))
    if row is None:
        return AgentModelRecord(owner_id=owner_id, agent_id=agent_id)
    try:
        value = AgentModelRecord.model_validate(row.payload)
    except ValidationError:
        raise LonoraError("agent_model_state_invalid", 409) from None
    if value.owner_id != owner_id or value.agent_id != agent_id:
        raise LonoraError("agent_model_scope_mismatch", 409)
    return value


async def agent_model_record(
    session: AsyncSession, owner_id: str, agent_id: str
) -> AgentModelRecord:
    await owned_agent(session, owner_id, agent_id)
    return await stored_agent_model(session, owner_id, agent_id)


async def agent_model_preference(
    session: AsyncSession, owner_id: str, agent_id: str
) -> AgentModelPreference | None:
    """The router's read: an unreadable record degrades to the global routes."""
    try:
        record = await stored_agent_model(session, owner_id, agent_id)
    except LonoraError:
        return None
    preference = record.preference
    return preference if preference.primary or preference.fallbacks else None


async def change_agent_model(
    session: AsyncSession, owner_id: str, agent_id: str, change: AgentModelChange
) -> AgentModelRecord:
    await owned_agent(session, owner_id, agent_id, lock=True)
    key = agent_model_key(owner_id, agent_id)
    row = await session.get(SettingRow, key, with_for_update=True, populate_existing=True)
    current = await stored_agent_model(session, owner_id, agent_id)
    if change.expected_revision is not None and change.expected_revision != current.revision:
        raise LonoraError("version_conflict", 409)
    record = AgentModelRecord(
        owner_id=owner_id,
        agent_id=agent_id,
        revision=current.revision + 1,
        preference=AgentModelPreference(primary=change.primary, fallbacks=change.fallbacks),
    )
    payload = record.model_dump(mode="json")
    if row is None:
        session.add(SettingRow(key=key, payload=payload))
    else:
        row.payload = payload
        row.updated_at = utcnow()
    await session.flush()
    emit(
        session,
        owner_id,
        "agent.model.updated",
        agent_id=agent_id,
        payload={"agent_id": agent_id, "revision": record.revision},
    )
    return record
