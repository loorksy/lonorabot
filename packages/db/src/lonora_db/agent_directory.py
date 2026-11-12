from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .agent_binding import scope_data
from .agent_creation import agent_origin, report_targets
from .lead import personal_agent_id, reached_ids
from .schema import AgentRow


async def agent_directory(
    session: AsyncSession, owner_id: str, agent_id: str, name: str | None = None
) -> list[dict[str, Any]]:
    """Read routing identities only; never expose private prompts or other owners' agents."""
    query = select(AgentRow).where(AgentRow.owner_id == owner_id)
    if name:
        query = query.where(AgentRow.name.icontains(name, autoescape=True))
    rows = (await session.scalars(query.order_by(AgentRow.created_at, AgentRow.id))).all()
    origins = {row.id: await agent_origin(session, owner_id, row.id) for row in rows}
    # The lead relation, visible to both sides: Lonora leads every team agent by its role
    # (3.3.1: two levels); no team agent leads another.
    supervised = set(await reached_ids(session, owner_id, agent_id))
    lead = await personal_agent_id(session, owner_id)
    supervisors = {lead} if lead is not None and lead != agent_id else set()
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
