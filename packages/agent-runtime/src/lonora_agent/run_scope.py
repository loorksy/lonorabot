"""The current Run of an Agent's tool call, checked against the call's owner, Agent, Thread
and lease (the skill lifecycle's guard)."""

from lonora_core.user_error import LonoraError
from lonora_db.runs import require_lease
from lonora_db.schema import RunRow, ThreadRow
from lonora_db.transactions import owned_agent
from lonora_tools.base import run_scope
from lonora_tools.context import ToolContext
from sqlalchemy.ext.asyncio import AsyncSession


async def scoped_run(
    session: AsyncSession, context: ToolContext, *, mutate: bool = False, helper: bool = False
) -> RunRow:
    """The current Run of this Agent's call.

    ``mutate`` writes are refused for a paused Agent and for a temporary helper (unless
    ``helper``); an observe-only wake has no financial effects, so it keeps them.
    """
    agent = await owned_agent(session, context.owner_id, context.agent_id, lock=mutate)
    run = await require_lease(session, context.lease, lock=mutate)
    thread = await session.get(ThreadRow, run.thread_id)
    if (
        not context.call_id
        or run.agent_id != context.agent_id
        or run.thread_id != context.thread_id
        or thread is None
        or thread.owner_id != context.owner_id
    ):
        raise LonoraError("workspace_scope_mismatch", 409)
    if mutate and (
        agent.paused or (run_scope(run.trigger, run.model_metadata) == "helper" and not helper)
    ):
        raise LonoraError("tool_not_allowed", 403)
    return run
