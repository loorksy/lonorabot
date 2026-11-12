"""Lonora's lead role (3.1, 14.3.15): built in, never a grant.

Lonora is the owner's one agent with role ``personal``. It reads every team agent's
conversations, work and memory (3.1.6) and steers their work by that role alone, so no
revocable record can take the lead's powers away. Every other agent is a team agent, and
no team agent reads or steers another (3.3.1: two levels, no supervision grants).
"""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentRow

LEAD_ROLE = "personal"


async def personal_agent_id(session: AsyncSession, owner_id: str) -> str | None:
    return await session.scalar(
        select(AgentRow.id).where(AgentRow.owner_id == owner_id, AgentRow.role == LEAD_ROLE)
    )


async def is_lead(session: AsyncSession, owner_id: str, agent_id: str) -> bool:
    return agent_id == await personal_agent_id(session, owner_id)


async def team_ids(session: AsyncSession, owner_id: str) -> list[str]:
    """Every team agent of the owner, in a stable order."""
    rows = await session.scalars(
        select(AgentRow.id)
        .where(AgentRow.owner_id == owner_id, AgentRow.role != LEAD_ROLE)
        .order_by(AgentRow.created_at, AgentRow.id)
    )
    return list(rows)


async def reached_ids(session: AsyncSession, owner_id: str, agent_id: str) -> list[str]:
    """The other agents this one reads and steers: every team agent for the lead, none for
    a team agent."""
    if await is_lead(session, owner_id, agent_id):
        return await team_ids(session, owner_id)
    return []


async def reaches(session: AsyncSession, owner_id: str, actor_id: str, agent_id: str) -> bool:
    """Whether this agent reads and steers that one: only the lead, over any team agent."""
    if actor_id == agent_id or not await is_lead(session, owner_id, actor_id):
        return False
    return (
        await session.scalar(
            select(AgentRow.id).where(AgentRow.owner_id == owner_id, AgentRow.id == agent_id)
        )
        is not None
    )
