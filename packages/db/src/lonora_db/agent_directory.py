from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentRow


async def agent_directory(
    session: AsyncSession, owner_id: str, agent_id: str, name: str | None = None
) -> list[dict[str, Any]]:
    """Read routing identities only; never expose private prompts or other owners' agents."""
    query = select(AgentRow).where(AgentRow.owner_id == owner_id)
    if name:
        query = query.where(AgentRow.name.icontains(name, autoescape=True))
    rows = (await session.scalars(query.order_by(AgentRow.created_at, AgentRow.id))).all()
    return [
        {"id": row.id, "name": row.name, "paused": row.paused, "is_self": row.id == agent_id}
        for row in rows
    ]
