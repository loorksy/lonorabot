"""One durable owner-wide identity, independent of its editable display name."""

from uuid import NAMESPACE_URL, uuid5

from lonora_contracts.domain import AgentCreate
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agents import create_agent
from .events import emit
from .schema import AgentRow, OwnerRow
from .threads import conversation_thread


async def ensure_personal_agent(session: AsyncSession, owner_id: str) -> AgentRow:
    row = await session.scalar(
        select(AgentRow).where(AgentRow.owner_id == owner_id, AgentRow.role == "personal")
    )
    if row:
        return row
    # Only the rare bootstrap path serializes; the partial unique index is a second boundary.
    owner = await session.get(OwnerRow, owner_id, with_for_update=True)
    if owner is None:
        raise LonoraError("owner_not_found", 404)
    row = await session.scalar(
        select(AgentRow).where(AgentRow.owner_id == owner_id, AgentRow.role == "personal")
    )
    if row:
        return row
    agent_id = str(uuid5(NAMESPACE_URL, f"lonora:personal-agent:{owner_id}"))
    row = await create_agent(session, owner_id, AgentCreate(name="Lonora"), agent_id=agent_id)
    row.role = "personal"
    await session.flush()
    thread = await conversation_thread(session, owner_id, row.id)
    emit(session, owner_id, "agent.personal_initialized", agent_id=row.id, thread_id=thread.id)
    return row


async def discover_specialists(
    session: AsyncSession, owner_id: str, account_id: str, broker_symbol: str, *, limit: int = 8
) -> list[AgentRow]:
    """Exact broker metadata, no display-name heuristics or implicit mass wake."""
    return list(
        (
            await session.scalars(
                select(AgentRow)
                .where(
                    AgentRow.owner_id == owner_id,
                    AgentRow.role == "specialist",
                    AgentRow.trading_account_id == account_id,
                    AgentRow.trading_symbol == broker_symbol,
                    AgentRow.paused.is_(False),
                )
                .order_by(AgentRow.created_at, AgentRow.id)
                .limit(min(max(limit, 1), 32))
            )
        ).all()
    )


async def account_event_agent(session: AsyncSession, owner_id: str) -> AgentRow:
    """One primary conversational owner for account events, never all specialists."""
    return await ensure_personal_agent(session, owner_id)
