"""Which commands receive the agent's `lonora` CLI token (7.3.3, 6.9).

``token_for_command`` is the token a command started for this run carries as
``LONORA_AGENT_TOKEN``: ``workspace_run`` passes it to the supervisor, which sets it in
that command's environment, so its children inherit it. Only a run of full scope has
one: a research subagent's command and an observe-only broker-activity wake get ``None``
(and ``workspace_run`` refuses those runs anyway), just as the door refuses them for the
trade tool (6.9).
"""

from dataclasses import dataclass

from lonora_db.cli_tokens import cli_token, owner_cli_tokens
from lonora_db.client import Database
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


async def token_for_command(
    session: AsyncSession, key: str, run_id: str, agent_id: str | None = None
) -> str | None:
    """``agent_id``: the agent whose Unix user runs the command; a run of another agent
    gets no token, so one agent's token never lands in another agent's process."""
    run = await session.get(RunRow, run_id)
    if run is None or (agent_id is not None and run.agent_id != agent_id):
        return None
    if not await full_ancestry(session, run):
        return None
    agent = await session.get(AgentRow, run.agent_id)
    if agent is None:
        return None
    return await cli_token(session, key, agent.owner_id, agent.id)


@dataclass(frozen=True)
class CommandTokens:
    """The owner's CLI tokens as the workspace tools need them."""

    db: Database
    key: str
    owner_id: str

    async def for_run(self, run_id: str, agent_id: str) -> str | None:
        async with self.db.sessions() as session, session.begin():
            return await token_for_command(session, self.key, run_id, agent_id)

    async def values(self) -> list[str]:
        async with self.db.sessions() as session:
            return await owner_cli_tokens(session, self.key, self.owner_id)
