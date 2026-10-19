"""Bounded retries reuse the same Run checkpoint and operation identities."""

from datetime import timedelta
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.tasks import TaskFailure, TaskRecovery
from lonora_core.runtime_failure import TRANSIENT_READ_CODES
from lonora_core.user_error import LonoraError
from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .client import Database
from .events import emit
from .schema import RunRow, ThreadRow, TicketRow, TradingJournalRow
from .tasks import get_task, save_task, task_state

TRANSIENT_CODES = TRANSIENT_READ_CODES | frozenset(
    {
        "model_provider_unavailable",
        "model_endpoint_unavailable",
        "model_rate_limited",
    }
)
PLAN_CODES = frozenset(
    {
        "model_request_rejected",
        "context_limit_exceeded",
        "tool_round_limit",
        "task_steps_incomplete",
    }
)
OWNER_CODES = frozenset(
    {
        "runtime_error",
        "skill_continuation_unavailable",
        "model_not_configured",
        "model_credentials_rejected",
        "model_response_invalid",
        "broker_unconfigured",
    }
)
FINANCIAL_REPLAY_TOOLS = frozenset({"trade_execute", "trade_close_positions", "goal_step_execute"})
CHECKPOINT_TOOLS = frozenset({"task_step_update"})


def has_unknown_mutation(run: RunRow, read_only_names: set[str]) -> bool:
    """Classification comes from the server Tool registry, never model declarations."""
    messages: list[dict[str, Any]] = run.execution_state.get("messages", [])
    resolved = {
        message.get("tool_call_id") for message in messages if message.get("role") == "tool"
    }
    return any(
        call.get("name") not in read_only_names | FINANCIAL_REPLAY_TOOLS | CHECKPOINT_TOOLS
        and call.get("id") not in resolved
        for message in messages
        for call in message.get("tool_calls", [])
    )


async def unresolved_financial(session: AsyncSession, run_id: str) -> bool:
    return (
        await session.scalar(
            select(TradingJournalRow.operation_id)
            .where(
                TradingJournalRow.status.in_(["submitted", "ambiguous"]),
                TradingJournalRow.execution_mode == "live",
                or_(
                    TradingJournalRow.result["details"]["lease"]["run_id"].as_string() == run_id,
                    TradingJournalRow.result["details"]["execution"]["run_id"].as_string()
                    == run_id,
                ),
            )
            .limit(1)
        )
        is not None
    )


async def record_failure(session: AsyncSession, run: RunRow, read_only_names: set[str]) -> None:
    identifier = run.model_metadata.get("task_id")
    if not identifier:
        return
    row = await session.get(TicketRow, identifier, with_for_update=True)
    if (
        row is None
        or row.agent_id != run.agent_id
        or row.thread_id != run.thread_id
        or not row.state.get("task")
    ):
        return
    state = task_state(row)
    if state.status in {"completed", "cancelled"} or state.control_requested == "cancel":
        return
    if state.failure and (state.failure.run_id, state.failure.lease_fence) == (
        run.id,
        run.lease_fence,
    ):
        return
    code = run.error_code or "runtime_error"
    recovery: TaskRecovery = "terminal"
    financial = await unresolved_financial(session, run.id)
    unknown = has_unknown_mutation(run, read_only_names)
    if financial or unknown:
        recovery = "reconcile"
    elif code in PLAN_CODES:
        recovery = "modify_plan"
    elif (
        code in TRANSIENT_CODES | OWNER_CODES
        and state.attempt < state.retry_policy.maximum_attempts
    ):
        recovery = "owner"
        remaining = [step for step in state.steps if step.state not in {"completed", "skipped"}]
        calls = [
            call
            for message in run.execution_state.get("messages", [])
            for call in message.get("tool_calls", [])
        ]
        if (
            code in TRANSIENT_CODES
            and state.retry_policy.mode == "automatic"
            and remaining
            and all(step.side_effect == "read_only" for step in remaining)
            and all(call.get("name") in read_only_names | CHECKPOINT_TOOLS for call in calls)
        ):
            recovery = "automatic"
    failure = TaskFailure(
        run_id=run.id,
        lease_fence=run.lease_fence,
        code=code,
        attempt=state.attempt,
        failed_step_id=next((step.id for step in state.steps if step.state == "running"), None),
        recovery=recovery,
        reconciliation="financial" if financial else "external" if unknown else None,
        next_retry_at=(
            utcnow()
            + timedelta(
                seconds=min(
                    300, state.retry_policy.initial_delay_seconds * 2 ** (state.attempt - 1)
                )
            )
        ).isoformat()
        if recovery == "automatic"
        else None,
    )
    state.failure = failure
    for step in state.steps:
        if step.state == "running":
            step.state = "failed"
    state.status = "waiting" if recovery == "automatic" else "failed"
    state.phase = "retry_wait" if recovery == "automatic" else "failed"
    state.waiting_reason = "retry_backoff" if recovery == "automatic" else None
    save_task(session, row, state)
    emit(
        session,
        row.owner_id,
        "task.retry_scheduled" if recovery == "automatic" else "task.failed",
        agent_id=row.agent_id,
        thread_id=state.origin_thread_id,
        run_id=run.id,
        payload={
            "id": row.id,
            "code": code,
            "recovery": recovery,
            "attempt": state.attempt,
            "next_retry_at": failure.next_retry_at,
        },
    )


async def resume_failure(
    session: AsyncSession,
    owner_id: str,
    task_id: str,
    *,
    expected_version: int | None = None,
    automatic: bool = False,
) -> TicketRow | None:
    original = await get_task(session, owner_id, task_id)
    failure = task_state(original).failure
    if failure is None:
        raise LonoraError("task_cannot_resume", 409)
    # Match admission's thread → Run lock order, then lock logical work.
    await session.get(ThreadRow, original.thread_id or "", with_for_update=True)
    run = await session.get(RunRow, failure.run_id, with_for_update=True, populate_existing=True)
    row = await get_task(session, owner_id, task_id, lock=True)
    state = task_state(row)
    if expected_version is not None and row.version != expected_version:
        raise LonoraError("version_conflict", 409)
    failure = state.failure
    if (
        failure is None
        or state.status not in {"waiting", "failed", "paused"}
        or run is None
        or run.status != "failed"
    ):
        if automatic:
            return None
        raise LonoraError("task_cannot_resume", 409)
    if (
        run.id != failure.run_id
        or run.lease_fence != failure.lease_fence
        or run.agent_id != row.agent_id
        or run.thread_id != row.thread_id
    ):
        raise LonoraError("task_run_mismatch", 409)
    if failure.recovery in {"modify_plan", "terminal"} or (
        failure.recovery == "reconcile" and failure.reconciliation != "financial"
    ):
        raise LonoraError(
            "task_reconciliation_required"
            if failure.recovery == "reconcile"
            else "task_cannot_resume",
            409,
        )
    if state.control_requested or state.attempt >= state.retry_policy.maximum_attempts:
        raise LonoraError("task_retry_limit", 409)
    if automatic:
        if (
            failure.recovery != "automatic"
            or not failure.next_retry_at
            or failure.next_retry_at > utcnow().isoformat()
        ):
            return None
    if await unresolved_financial(session, run.id):
        raise LonoraError("task_reconciliation_required", 409)
    state.attempt += 1
    for step in state.steps:
        if step.state == "failed":
            step.state = "pending"
    state.failure = failure.model_copy(update={"next_retry_at": None})
    state.status, state.phase, state.waiting_reason = "queued", "queued", None
    run.status, run.error_code, run.lease_expires_at = "queued", None, None
    run.model_metadata = {**run.model_metadata, "task_attempt": state.attempt}
    run.execution_state = {
        **run.execution_state,
        "prior_attempt_rounds": int(run.execution_state.get("prior_attempt_rounds", 0))
        + int(run.execution_state.get("rounds", 0)),
        "rounds": 0,
    }
    run.updated_at = utcnow()
    # execution_state, completed steps, call IDs and financial operation identities stay intact.
    save_task(session, row, state)
    emit(
        session,
        owner_id,
        "task.resumed",
        agent_id=row.agent_id,
        thread_id=state.origin_thread_id,
        run_id=run.id,
        payload={"id": row.id, "attempt": state.attempt, "automatic": automatic},
    )
    return row


async def retry_due_tasks(db: Database) -> int:
    async with db.sessions() as session:
        rows = list(
            await session.execute(
                select(TicketRow.id, TicketRow.owner_id)
                .where(
                    TicketRow.state["task"]["status"].as_string() == "waiting",
                    TicketRow.state["task"]["failure"]["recovery"].as_string() == "automatic",
                    TicketRow.state["task"]["failure"]["next_retry_at"].as_string()
                    <= utcnow().isoformat(),
                )
                .order_by(TicketRow.updated_at)
                .limit(50)
            )
        )
    changed = 0
    for task_id, owner_id in rows:
        async with db.sessions() as session, session.begin():
            try:
                changed += int(
                    await resume_failure(session, owner_id, task_id, automatic=True) is not None
                )
            except LonoraError as error:
                if error.code == "task_reconciliation_required":
                    row = await get_task(session, owner_id, task_id, lock=True)
                    state = task_state(row)
                    if state.failure:
                        state.failure.recovery, state.failure.next_retry_at = "reconcile", None
                        state.failure.reconciliation = "financial"
                        state.status, state.phase, state.waiting_reason = "failed", "failed", None
                        save_task(session, row, state)
                elif error.code not in {"task_not_found", "task_retry_limit"}:
                    raise
    return changed
