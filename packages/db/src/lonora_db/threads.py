from typing import Any

from lonora_contracts.domain import ThreadCreate
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentRow, GroupRow, ThreadRow
from .transactions import owned_agent


def thread_data(row: ThreadRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "group_id": row.group_id,
        "title": row.title,
        "created_at": row.created_at.isoformat(),
    }


async def create_thread(
    session: AsyncSession, owner_id: str, request: ThreadCreate, *, purpose: str = "conversation"
) -> ThreadRow:
    if purpose not in {"conversation", "work"}:
        raise LonoraError("thread_purpose_invalid", 422)
    if bool(request.agent_id) == bool(request.group_id):
        raise LonoraError("thread_target_required")
    if request.agent_id:
        await owned_agent(session, owner_id, request.agent_id)
    if request.group_id:
        group = await session.get(GroupRow, request.group_id)
        if group is None or group.owner_id != owner_id:
            raise LonoraError("group_not_found", 404)
    row = ThreadRow(owner_id=owner_id, purpose=purpose, **request.model_dump())
    session.add(row)
    await session.flush()
    return row


async def conversation_thread(session: AsyncSession, owner_id: str, agent_id: str) -> ThreadRow:
    """One atomic canonical direct conversation shared by owner messages and peer requests."""
    # Serialize canonical creation without blocking FK KEY SHARE on messages/runs.
    # FOR UPDATE here would invert agent/thread locks with an owner send or reverse peer.
    agent = await session.scalar(
        select(AgentRow)
        .where(AgentRow.id == agent_id, AgentRow.owner_id == owner_id)
        .with_for_update(key_share=True)
    )
    if agent is None:
        raise LonoraError("agent_not_found", 404)
    row = await session.scalar(
        select(ThreadRow)
        .where(
            ThreadRow.owner_id == owner_id,
            ThreadRow.agent_id == agent_id,
            ThreadRow.group_id.is_(None),
            ThreadRow.purpose == "conversation",
        )
        .order_by(ThreadRow.created_at, ThreadRow.id)
        .limit(1)
    )
    return (
        row
        if row is not None
        else await create_thread(session, owner_id, ThreadCreate(agent_id=agent_id, title=""))
    )


async def list_threads(
    session: AsyncSession, owner_id: str, agent_id: str | None = None
) -> list[ThreadRow]:
    query = select(ThreadRow).where(
        ThreadRow.owner_id == owner_id, ThreadRow.purpose == "conversation"
    )
    if agent_id:
        query = query.where(ThreadRow.agent_id == agent_id)
    return list(
        (await session.scalars(query.order_by(ThreadRow.created_at.desc()).limit(200))).all()
    )
