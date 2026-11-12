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


async def token_for_command(session: AsyncSession, key: str, run_id: str) -> str | None:
    run = await session.get(RunRow, run_id)
    if run is None:
        return None
    # Every ancestor too, as the door's ancestry walk does (6.9).
    current: RunRow | None = run
    seen: set[str] = set()
    while current is not None and current.id not in seen:
        if run_scope(current.trigger, current.model_metadata or {}) != "full":
            return None
        seen.add(current.id)
        parent = current.parent_run_id
        current = await session.get(RunRow, parent) if parent else None
    agent = await session.get(AgentRow, run.agent_id)
    if agent is None:
        return None
    return await cli_token(session, key, agent.owner_id, agent.id)
