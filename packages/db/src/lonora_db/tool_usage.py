"""Bounded per-agent recency of long-tail tools, promoted into later Runs.

Presentation memory only: which schemas a Run receives natively. It never
grants, widens or narrows authority; execution validates every call.
"""

from lonora_contracts.domain import utcnow
from sqlalchemy import delete, select
from sqlalchemy.dialects import postgresql, sqlite
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentToolUsageRow

MAX_REMEMBERED_TOOLS = 16


async def remembered_tools(
    session: AsyncSession, owner_id: str, agent_id: str, limit: int = MAX_REMEMBERED_TOOLS
) -> list[str]:
    """Most recently used first; frequency and name break ties deterministically."""
    return list(
        (
            await session.scalars(
                select(AgentToolUsageRow.tool_name)
                .where(
                    AgentToolUsageRow.owner_id == owner_id,
                    AgentToolUsageRow.agent_id == agent_id,
                )
                .order_by(
                    AgentToolUsageRow.last_used_at.desc(),
                    AgentToolUsageRow.uses.desc(),
                    AgentToolUsageRow.tool_name,
                )
                .limit(limit)
            )
        ).all()
    )


async def record_tool_use(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    tool_name: str,
    keep: int = MAX_REMEMBERED_TOOLS,
) -> None:
    """Upsert one use, then keep only the agent's ``keep`` most recent tools."""
    now = utcnow()
    dialect = postgresql if session.get_bind().dialect.name == "postgresql" else sqlite
    statement = dialect.insert(AgentToolUsageRow).values(
        agent_id=agent_id, tool_name=tool_name, owner_id=owner_id, uses=1, last_used_at=now
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=[AgentToolUsageRow.agent_id, AgentToolUsageRow.tool_name],
            set_={"uses": AgentToolUsageRow.uses + 1, "last_used_at": now},
        )
    )
    stale = (
        select(AgentToolUsageRow.tool_name)
        .where(AgentToolUsageRow.agent_id == agent_id)
        .order_by(
            AgentToolUsageRow.last_used_at.desc(),
            AgentToolUsageRow.uses.desc(),
            AgentToolUsageRow.tool_name,
        )
        .offset(keep)
    )
    await session.execute(
        delete(AgentToolUsageRow).where(
            AgentToolUsageRow.agent_id == agent_id,
            AgentToolUsageRow.tool_name.in_(stale),
        )
    )
