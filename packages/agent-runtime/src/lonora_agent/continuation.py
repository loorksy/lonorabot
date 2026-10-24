"""Bounded compute slices for the same durable Task and fenced Run.

Adapt the continuation boundary demonstrated by nanobot, not its process-local
queue. Existing checkpoints, the Run claimant and effect owners remain the only
persistence, scheduling and financial-recovery mechanisms.
"""

from typing import Any, cast

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.runs import checkpoint, require_lease
from lonora_db.schema import TicketRow
from lonora_db.tasks import checkpoint_task
from lonora_tools.context import ToolContext

from .environment import environment_state
from .tasks import TaskSuspended

MAXIMUM_SLICES = 4


def slice_limit(state: dict[str, Any], maximum_rounds: int) -> int:
    """Pin the original compute budget; restarts/config changes cannot reset it.

    Ordinary Runs keep one slice. Only ``schedule_task_continuation`` can advance
    this server-owned counter, after verifying the real Task binding.
    """
    if type(maximum_rounds) is not int or maximum_rounds < 1:
        raise LonoraError("task_continuation_budget_invalid", 409)
    saved = state.setdefault(
        "task_continuation",
        {"version": 1, "slice": 1, "rounds_per_slice": maximum_rounds},
    )
    if not isinstance(saved, dict):
        raise LonoraError("task_continuation_state_invalid", 409)
    value = cast(dict[str, Any], saved)
    count, rounds = value.get("slice"), value.get("rounds_per_slice")
    if (
        value.get("version") != 1
        or type(count) is not int
        or not 1 <= count <= MAXIMUM_SLICES
        or type(rounds) is not int
        or rounds < 1
    ):
        raise LonoraError("task_continuation_state_invalid", 409)
    return count * rounds


async def schedule_task_continuation(
    context: ToolContext, state: dict[str, Any], maximum_rounds: int
) -> bool:
    """Checkpoint another finite slice, without replaying or replacing any call.

    The caller releases its worker through the existing ``ToolRetryScheduled``
    path. A crash before release is safe: the new budget and unchanged pending
    calls already belong to this same Run and are recovered under a new fence.
    """
    limit = slice_limit(state, maximum_rounds)
    if state.get("rounds", 0) != limit:
        return False
    saved = cast(dict[str, Any], state["task_continuation"])
    suspended = False
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease)
        task_id = run.model_metadata.get("task_id")
        if not isinstance(task_id, str):
            return False
        task = await session.get(TicketRow, task_id)
        if (
            task is None
            or task.owner_id != context.owner_id
            or task.agent_id != run.agent_id
            or task.thread_id != run.thread_id
            or task.payload.get("run_id") != run.id
            or not task.state.get("task")
        ):
            raise LonoraError("task_run_mismatch", 409)
        # Apply owner pause/cancel at this last boundary too. A control arriving
        # after the loop's preceding checkpoint must not become a budget failure.
        suspended = await checkpoint_task(session, context.lease)
        if not suspended:
            if saved["slice"] >= MAXIMUM_SLICES:
                return False
            saved["slice"] += 1
            environment_state(state)["retry"] = {
                "not_before": utcnow().isoformat(),
                "reason_code": "task_continuation",
            }
            await checkpoint(session, context.lease, state)
    if suspended:
        raise TaskSuspended()
    return True
