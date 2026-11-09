from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_binding import scope_data
from .agent_creation import agent_origin, report_targets
from .schema import AgentRow
from .supervision import supervised_ids, supervisor_ids


async def agent_directory(
    session: AsyncSession, owner_id: str, agent_id: str, name: str | None = None
) -> list[dict[str, Any]]:
    """Read routing identities only; never expose private prompts or other owners' agents."""
    query = select(AgentRow).where(AgentRow.owner_id == owner_id)
    if name:
        query = query.where(AgentRow.name.icontains(name, autoescape=True))
    rows = (await session.scalars(query.order_by(AgentRow.created_at, AgentRow.id))).all()
    origins = {row.id: await agent_origin(session, owner_id, row.id) for row in rows}
    # Supervision is visible to both sides: whom this agent supervises, who supervises it.
    supervised = set(await supervised_ids(session, owner_id, agent_id))
    supervisors = set(await supervisor_ids(session, owner_id, agent_id))
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
            "template": origins[row.id].get("template"),
            # Peer links: the agents this one reports important findings to.
            "reports_to": report_targets(origins[row.id]),
            "you_supervise": row.id in supervised,
            "supervises_you": row.id in supervisors,
        }
        for row in rows
    ]
