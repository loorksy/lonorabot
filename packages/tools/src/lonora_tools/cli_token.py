"""Which commands receive the agent's `lonora` CLI token (7.3.3, 6.9).

The workspace calls this when it starts a command for a run and sets the result as
``LONORA_AGENT_TOKEN``. Only a run of full scope gets it: a research subagent's command
and an observe-only broker-activity wake get none, so their ``lonora`` calls exit 77,
just as the door refuses those runs for the trade tool (6.9).
"""

from lonora_db.cli_tokens import cli_token
from lonora_db.schema import AgentRow, RunRow
from sqlalchemy.ext.asyncio import AsyncSession

from .base import run_scope


# The door's own bound on the parent-run walk (``require_goal_lineage``, execution.py).
MAXIMUM_ANCESTRY = 16


async def full_ancestry(session: AsyncSession, run: RunRow) -> bool:
    """The run and every ancestor are of full scope, as the door's walk requires (6.9).
    A cycle, a missing ancestor or a chain past the door's bound is not."""
    current, seen = run, {run.id}
    for _ in range(MAXIMUM_ANCESTRY + 1):
        if run_scope(current.trigger, current.model_metadata or {}) != "full":
            return False
        parent = current.parent_run_id
        if not parent:
            return True
        if parent in seen:
            return False
        seen.add(parent)
        found = await session.get(RunRow, parent)
        if found is None:
            return False
        current = found
    return False


async def token_for_command(session: AsyncSession, key: str, run_id: str) -> str | None:
    run = await session.get(RunRow, run_id)
    if run is None or not await full_ancestry(session, run):
        return None
    agent = await session.get(AgentRow, run.agent_id)
    if agent is None:
        return None
    return await cli_token(session, key, agent.owner_id, agent.id)
