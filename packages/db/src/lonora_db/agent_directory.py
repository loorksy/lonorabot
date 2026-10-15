from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_binding import scope_data
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
        {
            "id": row.id,
            "name": row.name,
            "title": row.title,
            "description": row.description,
            "paused": row.paused,
            "is_self": row.id == agent_id,
            "role": row.role,
            "scope": scope_data(row),
            "trading_account_id": row.trading_account_id,
            "trading_symbol": row.trading_symbol,
        }
        for row in rows
    ]
