"""The per-agent authority lock shared by grants, permission changes and the executor."""

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


async def authority_lock(session: AsyncSession, agent_id: str) -> None:
    """Serialize every change to an agent's money authority with its final send check.

    The key prefix predates the retired Super Bot and is kept, so a process running the
    previous release still takes the same lock during a restart.
    """
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key,0))"),
            {"key": "super-bot:" + agent_id},
        )
