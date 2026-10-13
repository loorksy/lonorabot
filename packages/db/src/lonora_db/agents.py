from typing import Any

from lonora_contracts.domain import AgentCreate, AgentUpdate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentRow, MemoryRow
from .transactions import owned_agent


def agent_data(row: AgentRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "title": row.title,
        "description": row.description,
        "avatar": row.avatar,
        "color": row.color,
        "instructions": row.instructions,
        "paused": row.paused,
        "parent_id": row.parent_id,
        "created_at": row.created_at.isoformat(),
    }


async def create_agent(
    session: AsyncSession,
    owner_id: str,
    request: AgentCreate,
    parent_id: str | None = None,
    agent_id: str | None = None,
) -> AgentRow:
    if parent_id:
        await owned_agent(session, owner_id, parent_id)
    row = AgentRow(owner_id=owner_id, parent_id=parent_id, **request.model_dump())
    if agent_id:
        row.id = agent_id
    session.add(row)
    await session.flush()
    session.add(MemoryRow(agent_id=row.id))
    return row


async def list_agents(session: AsyncSession, owner_id: str) -> list[AgentRow]:
    return list(
        (
            await session.scalars(
                select(AgentRow).where(AgentRow.owner_id == owner_id).order_by(AgentRow.created_at)
            )
        ).all()
    )


async def update_agent(
    session: AsyncSession, owner_id: str, agent_id: str, request: AgentUpdate
) -> AgentRow:
    row = await owned_agent(session, owner_id, agent_id, lock=True)
    for key, value in request.model_dump(exclude_none=True).items():
        setattr(row, key, value)
    return row
