"""``lonora wake <agent-handle> "<text>"`` (7.3.7, 11.8).

Starts a run of the agent with that @handle in its own conversation. The run names the
calling agent, and the script's text reaches the model only as data (6.10): it is kept in
the run's metadata, never in ``run.prompt``, which the context builder would deliver as a
request.
"""

from lonora_contracts.runs import RunRequest
from lonora_core.user_error import LonoraError
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .runs import create_run
from .schema import AgentRow, RunRow
from .threads import conversation_thread

TRIGGER = "workspace_wake"
WAKE_KEY = "workspace_wake"
MAXIMUM_TEXT = 4000


async def agent_by_handle(session: AsyncSession, owner_id: str, handle: str) -> AgentRow:
    """The agent an @handle names. A handle is ``@`` plus the agent's name, as an @mention
    in chat is; a name several agents share names none of them."""
    name = handle.removeprefix("@").strip()
    rows = (
        await session.scalars(
            select(AgentRow).where(
                AgentRow.owner_id == owner_id, func.lower(AgentRow.name) == name.lower()
            )
        )
    ).all()
    if not name or not rows:
        raise LonoraError("agent_not_found", 404)
    if len(rows) > 1:
        raise LonoraError("agent_handle_ambiguous", 409)
    return rows[0]


async def wake_by_handle(session: AsyncSession, caller: AgentRow, handle: str, text: str) -> RunRow:
    target = await agent_by_handle(session, caller.owner_id, handle)
    thread = await conversation_thread(session, caller.owner_id, target.id)
    return await create_run(
        session,
        caller.owner_id,
        RunRequest(
            thread_id=thread.id,
            agent_id=target.id,
            trigger=TRIGGER,
            metadata={
                WAKE_KEY: {"caller_agent_id": caller.id, "caller_name": caller.name, "text": text}
            },
        ),
    )
