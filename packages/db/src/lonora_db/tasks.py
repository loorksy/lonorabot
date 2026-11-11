"""Task lifecycle backed by the existing ticket, run and event ledger."""

import json
from typing import Any, cast

from lonora_contracts.domain import ThreadCreate, utcnow
from lonora_contracts.runs import Lease, RunRequest
from lonora_contracts.tasks import TaskControl, TaskCreate, TaskState, TaskStatus, TaskStepUpdate
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .market_watches import settle_task_watches
from .runs import create_run, inherited_authority, require_lease
from .schema import BoardRow, EventRow, RunRow, TicketRow, TradeApprovalRow
from .threads import create_thread
from .transactions import owned_agent, owned_thread

# Unfinished work handed to its owner instead of failing the Run.
OWNER_ATTENTION = "owner_attention"
# Read by the agent loop: a Task control resumed work held for owner attention.
ATTENTION_RESUMED = "owner_attention_resumed"


def attention_question(run: RunRow) -> dict[str, Any] | None:
    """The pending owner-attention question that holds this Run, if any."""
    question = run.execution_state.get("pending_input_request")
    if not isinstance(question, dict):
        return None
    value = cast(dict[str, Any], question)
    return value if value.get("kind") == OWNER_ATTENTION else None


def release_attention(run: RunRow, action: str) -> bool:
    """Requeue a Run held for owner attention, keeping its checkpoint.

    The unanswered question is cancelled as for any superseded question, and the
    loop starts a new review epoch (a new budget at a limit) on its next claim.
    """
    question = attention_question(run)
    if question is None or run.status not in {"waiting_input", "waiting_takeover"}:
        return False
    history = [
        {**item, "status": "cancelled"}
        if item.get("id") == question.get("id") and item.get("status") == "pending"
        else item
        for item in run.execution_state.get("input_requests", [])
    ]
    state: dict[str, Any] = {
        **run.execution_state,
        "input_requests": history,
        ATTENTION_RESUMED: {"action": action, "question_id": question.get("id")},
    }
    state.pop("pending_input_request", None)
    run.execution_state = state
    run.status = "queued"
    run.lease_expires_at = None
    return True


async def get_task(
    session: AsyncSession, owner_id: str, task_id: str, *, lock: bool = False
) -> TicketRow:
    query = select(TicketRow).where(TicketRow.id == task_id, TicketRow.owner_id == owner_id)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query.execution_options(populate_existing=True))
    if row is None or not row.state.get("task"):
        raise LonoraError("task_not_found", 404)
    return row


def task_state(row: TicketRow) -> TaskState:
    return TaskState.model_validate(row.state["task"])


def is_continuous_task(state: TaskState, run: RunRow) -> bool:
    """Legacy account-management work already has an explicitly ongoing purpose.

    Infer that purpose only for its existing Run; never revive terminal work or
    infer financial permission from this lifecycle property.
    """
    return state.completion_mode == "continuous" or bool(
        run.model_metadata.get("account_management_id")
    )


def save_task(session: AsyncSession, row: TicketRow, state: TaskState) -> None:
    row.state = {**row.state, "task": state.model_dump(mode="json")}
    row.payload = {
        **row.payload,
        "status": {
            "queued": "todo",
            "running": "working",
            "paused": "waiting",
        }.get(state.status, state.status),
    }
    row.updated_at = utcnow()
    row.version += 1
    emit(
        session,
        row.owner_id,
        "task.updated",
        agent_id=row.agent_id,
        thread_id=state.origin_thread_id,
        payload={
            "id": row.id,
            "version": row.version,
            "status": state.status,
            "waiting_reason": state.waiting_reason,
        },
    )


def finish_task(session: AsyncSession, row: TicketRow, status: TaskStatus) -> None:
    """Project a terminal attempt without reviving cancelled durable work.

    Workers return outcomes asynchronously. A completed/failed attempt arriving
    after an owner cancellation must not replace the owner's durable decision.
    """
    if status not in {"completed", "failed", "cancelled"}:
        raise LonoraError("task_terminal_status_required", 409)
    state = task_state(row)
    if state.status in {"completed", "failed", "cancelled"}:
        # Repair older contradictory projections without changing terminal truth.
        if row.payload.get("status") != state.status:
            save_task(session, row, state)
        return
    if state.control_requested == "cancel":
        status = "cancelled"
    elif state.control_requested == "complete":
        status = "completed"
    elif status == "completed" and state.completion_mode == "continuous":
        raise LonoraError("task_wait_required", 409)
    if status == "failed" and state.status == "waiting" and state.waiting_reason == "retry_backoff":
        return
    state.status, state.phase, state.control_requested = status, status, None
    state.waiting_reason = None
    save_task(session, row, state)


async def create_task(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    origin_thread_id: str,
    request: TaskCreate,
    task_id: str | None = None,
    *,
    starter: RunRow | None = None,
) -> TicketRow:
    await owned_agent(session, owner_id, agent_id)
    origin = await owned_thread(session, owner_id, origin_thread_id)
    if origin.agent_id != agent_id:
        raise LonoraError("agent_thread_mismatch", 409)
    if task_id:
        prior = await session.get(TicketRow, task_id)
        if prior:
            if prior.owner_id != owner_id or prior.agent_id != agent_id:
                raise LonoraError("task_not_found", 404)
            if (
                prior.payload.get("title") != request.title
                or prior.payload.get("description") != request.description
                or prior.state.get("task", {}).get("origin_thread_id") != origin_thread_id
                or task_state(prior).completion_mode != request.completion_mode
            ):
                raise LonoraError("task_intent_conflict", 409)
            return prior
    board = BoardRow(
        owner_id=owner_id,
        agent_id=agent_id,
        payload={"title": request.title, "columns": ["todo", "working", "done"]},
    )
    session.add(board)
    await session.flush()
    work = await create_thread(
        session, owner_id, ThreadCreate(agent_id=agent_id, title=request.title), purpose="work"
    )
    row = TicketRow(
        owner_id=owner_id,
        agent_id=agent_id,
        thread_id=work.id,
        payload={
            "board_id": board.id,
            "title": request.title,
            "description": request.description,
            "status": "todo",
        },
        state={
            "task": TaskState(
                origin_thread_id=origin_thread_id,
                completion_mode=request.completion_mode,
                steps=request.steps,
                retry_policy=request.retry_policy,
                due_at=request.due_at.isoformat() if request.due_at else None,
                completion_criteria=request.completion_criteria,
            ).model_dump(mode="json")
        },
    )
    if task_id:
        row.id = task_id
    session.add(row)
    await session.flush()
    from .genui_taint import taint_row_from

    # A Task tainted work started is tainted for good, and so is every Run it starts.
    await taint_row_from(session, starter, "ticket", row.id)
    run = await create_run(
        session,
        owner_id,
        RunRequest(
            thread_id=work.id,
            agent_id=agent_id,
            trigger="tickets",
            prompt=task_prompt(request),
            metadata={
                "ticket_id": row.id,
                "task_id": row.id,
                "origin_thread_id": origin_thread_id,
                "lane": "work",
                # The run that started it: a retry of that run must not repeat this work.
                **({"started_by_run_id": starter.id} if starter else {}),
                **inherited_authority(starter),
            },
        ),
    )
    row.payload = {**row.payload, "run_id": run.id}
    emit(
        session,
        owner_id,
        "task.created",
        thread_id=origin_thread_id,
        agent_id=agent_id,
        run_id=run.id,
        payload={"id": row.id},
    )
    return row


def task_prompt(request: TaskCreate) -> str:
    lines = [request.title, request.description]
    if request.completion_criteria:
        lines.append("Completion criterion: " + request.completion_criteria)
    if request.due_at:
        lines.append("Due by: " + request.due_at.isoformat())
    return "\n".join(line for line in lines if line)


async def task_runs(session: AsyncSession, row: TicketRow) -> list[RunRow]:
    return list(
        await session.scalars(
            select(RunRow)
            .where(RunRow.thread_id == row.thread_id, RunRow.agent_id == row.agent_id)
            .order_by(RunRow.created_at.desc())
            .limit(20)
        )
    )


async def snapshot(session: AsyncSession, row: TicketRow) -> dict[str, Any]:
    state = task_state(row)
    runs = await task_runs(session, row)
    active = next(
        (
            run
            for run in runs
            if run.status in {"queued", "leased", "running", "waiting_input", "waiting_takeover"}
        ),
        None,
    )
    status = state.status
    terminal = state.status in {"completed", "failed", "cancelled"}
    if (
        not terminal
        and not active
        and state.status != "paused"
        and state.waiting_reason != "retry_backoff"
        and runs
        and runs[0].status in {"completed", "failed", "cancelled"}
    ):
        status = runs[0].status
    if active and not terminal and state.status != "paused":
        status = (
            "running"
            if active.status in {"leased", "running"}
            else "waiting"
            if active.status.startswith("waiting")
            else "queued"
        )
    recent = (
        list(
            await session.scalars(
                select(EventRow)
                .where(
                    EventRow.run_id.in_([run.id for run in runs]),
                    EventRow.kind.in_(
                        [
                            "tool.started",
                            "tool.completed",
                            "tool.cancelled",
                            "run.reply_started",
                            "run.waiting_input",
                        ]
                    ),
                )
                .order_by(EventRow.cursor.desc())
                .limit(20)
            )
        )
        if runs
        else []
    )
    pending_tools: dict[str, dict[str, Any]] = {}
    for event in recent:
        call_id = event.payload.get("call_id")
        if call_id and call_id not in pending_tools:
            pending_tools[call_id] = {
                "name": event.payload.get("name"),
                "active": event.kind == "tool.started",
            }
    approval_pending = (
        await session.scalar(
            select(TradeApprovalRow.id)
            .where(TradeApprovalRow.run_id == active.id, TradeApprovalRow.status == "pending")
            .limit(1)
        )
        if active
        else None
    )
    phase = (
        "executing"
        if any(tool["active"] for tool in pending_tools.values()) and active and not terminal
        else "thinking"
        if active and active.status == "running" and not terminal
        else state.phase
        if state.waiting_reason == "retry_backoff"
        else status
    )
    from .task_recovery import unresolved_financial

    recoverable_failure = (
        state.failure is not None
        and (
            state.failure.recovery == "owner"
            or (
                state.failure.recovery == "reconcile"
                and state.failure.reconciliation == "financial"
                and not await unresolved_financial(session, state.failure.run_id)
            )
        )
        and state.attempt < state.retry_policy.maximum_attempts
    )
    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "title": row.payload["title"],
        "description": row.payload.get("description", ""),
        "version": row.version,
        **state.model_dump(mode="json"),
        "status": status,
        "work_thread_id": row.thread_id,
        "phase": phase,
        "waiting_reason": (
            "approval"
            if approval_pending
            else OWNER_ATTENTION
            if state.waiting_reason == OWNER_ATTENTION
            else "user_input"
        )
        if active and active.status == "waiting_input"
        else state.waiting_reason,
        "active_tools": [tool["name"] for tool in pending_tools.values() if tool["active"]]
        if not terminal
        else [],
        "runs": [
            {
                "id": run.id,
                "status": run.status,
                "error_code": run.error_code,
                "updated_at": run.updated_at.isoformat(),
            }
            for run in runs
        ],
        "can_pause": status in {"queued", "running", "waiting"},
        "can_resume": status == "paused"
        or (status == "failed" and recoverable_failure)
        or (
            status == "waiting"
            and active is not None
            and active.status == "waiting_input"
            and attention_question(active) is not None
        ),
        "can_cancel": status not in {"completed", "cancelled"},
    }


async def control_task(
    session: AsyncSession,
    owner_id: str,
    request: TaskControl,
    *,
    agent_id: str | None = None,
    owner_message: bool = False,
    complete: bool = False,
) -> TicketRow:
    """Pause, resume, cancel or revise a Task; ``complete`` turns the owner's cancel into
    «تحديد كمكتملة» (the same stop, recorded as completed)."""
    from .supervision import owner_takes_over, refuse_held

    row = await get_task(session, owner_id, request.task_id)
    if agent_id and row.agent_id != agent_id:
        raise LonoraError("task_agent_mismatch", 403)
    if agent_id is None:
        # The owner's pause, resume or cancel wins over a supervisor's pause of this Task.
        if request.action != "revise":
            await owner_takes_over(
                session,
                owner_id,
                "task",
                row.id,
                paused=request.action == "pause",
                agent_id=row.agent_id,
            )
    elif request.action == "resume":
        await refuse_held(session, owner_id, "task", row.id, agent_id, owner_message=owner_message)
    if row.version != request.expected_version:
        raise LonoraError("version_conflict", 409)
    state = task_state(row)
    retry_control = state.failure and (
        state.status == "failed"
        or state.waiting_reason == "retry_backoff"
        or state.phase == "retry_paused"
    )
    if retry_control and request.action == "resume":
        from .task_recovery import resume_failure

        resumed = await resume_failure(
            session, owner_id, row.id, expected_version=request.expected_version
        )
        if resumed is None:
            raise LonoraError("task_cannot_resume", 409)
        return resumed
    if retry_control and request.action in {"pause", "cancel", "revise"}:
        assert state.failure is not None
        failed_run = await session.get(
            RunRow, state.failure.run_id, with_for_update=True, populate_existing=True
        )
        row = await get_task(session, owner_id, row.id, lock=True)
        if row.version != request.expected_version:
            raise LonoraError("version_conflict", 409)
        state = task_state(row)
        if not failed_run or failed_run.status != "failed" or not state.failure:
            raise LonoraError("task_cannot_resume", 409)
        if request.action == "revise":
            revise_task(state, request)
            if state.failure.recovery == "modify_plan":
                state.failure.recovery = "owner"
        else:
            if request.action == "pause" and state.status != "waiting":
                raise LonoraError("task_cannot_pause", 409)
            state.failure.next_retry_at = None
            state.status = "paused" if request.action == "pause" else "cancelled"
            state.phase = "retry_paused" if request.action == "pause" else "cancelled"
            state.waiting_reason, state.control_requested = None, None
            if request.action == "cancel":
                await cancel_task_approvals(session, failed_run.id)
        save_task(session, row, owner_completed(state) if complete else state)
        await settle_task_watches(session, row)
        return row
    if state.status == "failed" and request.action == "cancel":
        row = await get_task(session, owner_id, row.id, lock=True)
        if row.version != request.expected_version:
            raise LonoraError("version_conflict", 409)
        state = task_state(row)
        state.status, state.phase, state.control_requested = "cancelled", "cancelled", None
        if state.failure:
            state.failure.next_retry_at = None
        save_task(session, row, state)
        await settle_task_watches(session, row)
        return row
    if state.status in {"completed", "failed", "cancelled"}:
        raise LonoraError("task_terminal", 409)
    runs = await task_runs(session, row)
    run = next(
        (
            run
            for run in runs
            if run.status in {"queued", "leased", "running", "waiting_input", "waiting_takeover"}
        ),
        None,
    )
    if not run:
        raise LonoraError("task_run_not_found", 409)
    run = await session.get(RunRow, run.id, with_for_update=True, populate_existing=True)
    if run is None:
        raise LonoraError("task_run_not_found", 409)
    row = await get_task(session, owner_id, request.task_id, lock=True)
    if row.version != request.expected_version:
        raise LonoraError("version_conflict", 409)
    state = task_state(row)
    if run.status not in {
        "queued",
        "leased",
        "running",
        "waiting_input",
        "waiting_takeover",
    } or state.status in {"completed", "failed", "cancelled"}:
        raise LonoraError("task_terminal", 409)
    if request.action == "resume":
        attention = run.status == "waiting_input" and attention_question(run) is not None
        if not attention and (state.status != "paused" or run.status != "waiting_takeover"):
            raise LonoraError("task_cannot_resume", 409)
        # A Task paused while held for attention resumes the work, not the question.
        if not release_attention(run, "resume"):
            run.status = "queued"
        state.status, state.phase, state.control_requested = "queued", "queued", None
        if state.waiting_reason == OWNER_ATTENTION:
            state.waiting_reason = None
    elif request.action == "revise":
        revise_task(state, request)
        environment = dict(run.execution_state.get("environment", {}))
        if run.status == "waiting_input" and release_attention(run, "revise"):
            # The revised plan reaches the model at its next task checkpoint.
            state.status, state.phase, state.waiting_reason = "queued", "queued", None
        elif environment.get("wait"):
            environment.pop("wait", None)
            environment["phase"] = "revalidating"
            run.execution_state = {**run.execution_state, "environment": environment}
            if state.status == "waiting":
                run.status = "queued"
                state.status, state.waiting_reason = "queued", None
    else:
        state.control_requested = request.action
        if run.status in {"queued", "waiting_input", "waiting_takeover"}:
            run.status = "waiting_takeover" if request.action == "pause" else "cancelled"
            state.status = "paused" if request.action == "pause" else "cancelled"
            state.phase = state.status
            state.control_requested = None
        if request.action == "cancel":
            approvals = await session.scalars(
                select(TradeApprovalRow).where(
                    TradeApprovalRow.run_id == run.id,
                    TradeApprovalRow.status.in_(
                        ["pending"]
                        if run.status in {"leased", "running"}
                        else ["pending", "approved"]
                    ),
                )
            )
            from .trade_approvals import approval_event

            for approval in approvals:
                approval.status = "cancelled"
                approval_event(session, approval)
    save_task(session, row, owner_completed(state) if complete else state)
    await settle_task_watches(session, row)
    return row


def owner_completed(state: TaskState) -> TaskState:
    if state.status == "cancelled":
        state.status, state.phase = "completed", "completed"
    elif state.control_requested == "cancel":
        state.control_requested = "complete"
    return state


async def complete_task(
    session: AsyncSession, owner_id: str, task_id: str, expected_version: int
) -> TicketRow:
    """The owner's «تحديد كمكتملة»: the work stops as on a cancel and the Task reads completed.

    Stopping releases the run exactly like the owner's cancel (pending trade approvals are
    cancelled, never approved); only the final status differs. Agents have no route here.
    """
    row = await get_task(session, owner_id, task_id)
    if row.version != expected_version:
        raise LonoraError("version_conflict", 409)
    state = task_state(row)
    if state.status in {"completed", "cancelled"}:
        raise LonoraError("task_terminal", 409)
    if state.status == "failed" or not await active_task_run(session, row):
        from .supervision import owner_takes_over

        # The owner's decision wins over a supervisor's hold, as with the owner's cancel.
        await owner_takes_over(
            session, owner_id, "task", row.id, paused=False, agent_id=row.agent_id
        )
        row = await get_task(session, owner_id, task_id, lock=True)
        if row.version != expected_version:
            raise LonoraError("version_conflict", 409)
        state = task_state(row)
        state.status, state.phase = "completed", "completed"
        state.control_requested, state.waiting_reason = None, None
        if state.failure:
            state.failure.next_retry_at = None
        # As the owner's cancel does: nothing this Task's runs asked for stays decidable.
        for run in await task_runs(session, row):
            await cancel_task_approvals(session, run.id)
        save_task(session, row, state)
        await settle_task_watches(session, row)
        return row
    return await control_task(
        session,
        owner_id,
        TaskControl(task_id=task_id, action="cancel", expected_version=expected_version),
        complete=True,
    )


async def active_task_run(session: AsyncSession, row: TicketRow) -> RunRow | None:
    return next(
        (
            run
            for run in await task_runs(session, row)
            if run.status in {"queued", "leased", "running", "waiting_input", "waiting_takeover"}
        ),
        None,
    )


def revise_task(state: TaskState, request: TaskControl) -> None:
    if not request.instruction and request.steps is None:
        raise LonoraError("task_revision_empty", 422)
    if request.steps is not None:
        if len({step.id for step in request.steps}) != len(request.steps):
            raise LonoraError("task_step_duplicate", 422)
        completed = {
            step.id: step for step in state.steps if step.state in {"completed", "skipped"}
        }
        if any(
            step.state in {"completed", "skipped"} and step.id not in completed
            for step in request.steps
        ):
            raise LonoraError("task_step_evidence_required", 409)
        if any(
            next((step for step in request.steps if step.id == key), None) != value
            for key, value in completed.items()
        ):
            raise LonoraError("task_completed_step_immutable", 409)
        state.steps = request.steps
    state.instruction = request.instruction
    state.plan_revision += 1


async def checkpoint_task(session: AsyncSession, lease: Lease) -> bool:
    run = await require_lease(session, lease, lock=True)
    task_id = run.model_metadata.get("task_id")
    if not task_id:
        return False
    row = await session.get(TicketRow, task_id, with_for_update=True)
    if row is None or row.agent_id != run.agent_id or row.thread_id != run.thread_id:
        raise LonoraError("task_run_mismatch", 409)
    run = await require_lease(session, lease, lock=True)
    state = task_state(row)
    state.last_checkpoint_at = utcnow().isoformat()
    if state.status in {"paused", "completed", "failed", "cancelled"}:
        run.status = "waiting_takeover" if state.status == "paused" else "cancelled"
        run.lease_expires_at = None
        return True
    if state.control_requested:
        pause = state.control_requested == "pause"
        run.status = "waiting_takeover" if pause else "cancelled"
        run.lease_expires_at = None
        state.status = (
            "paused"
            if pause
            else "completed"
            if state.control_requested == "complete"
            else "cancelled"
        )
        state.phase, state.control_requested = state.status, None
        save_task(session, row, state)
        return True
    changed = state.status != "running"
    state.status, state.phase = "running", "executing"
    if state.waiting_reason == OWNER_ATTENTION:
        # The owner's reply resumed the same checkpoint.
        state.waiting_reason = None
    if changed:
        save_task(session, row, state)
    else:
        row.state = {**row.state, "task": state.model_dump(mode="json")}
        row.updated_at = utcnow()
    return False


async def update_task_step(
    session: AsyncSession, lease: Lease, request: TaskStepUpdate
) -> TicketRow:
    run = await require_lease(session, lease, lock=True)
    row = await session.get(TicketRow, run.model_metadata.get("task_id", ""), with_for_update=True)
    if row is None or row.agent_id != run.agent_id or row.thread_id != run.thread_id:
        raise LonoraError("task_run_mismatch", 409)
    state = task_state(row)
    if state.status in {"paused", "cancelled", "completed", "failed"} or state.control_requested:
        raise LonoraError("task_not_running", 409)
    if state.plan_revision != request.plan_revision:
        raise LonoraError("task_plan_changed", 409)
    step = next((item for item in state.steps if item.id == request.step_id), None)
    if step is None:
        raise LonoraError("task_step_not_found", 404)
    if step.state in {"completed", "skipped"}:
        if step.state == request.state and step.evidence_call_ids == request.evidence_call_ids:
            return row
        raise LonoraError("task_completed_step_immutable", 409)
    if request.state == "completed":
        if not request.evidence_call_ids:
            raise LonoraError("task_step_evidence_required", 409)
        names: dict[str, str] = {}
        successful: set[str] = set()
        for execution in await task_runs(session, row):
            for message in execution.execution_state.get("messages", []):
                for call in message.get("tool_calls", []):
                    names[str(call["id"])] = str(call["name"])
                if message.get("role") != "tool":
                    continue
                try:
                    raw_result = json.loads(message.get("content", ""))
                except (ValueError, TypeError):
                    continue
                if not isinstance(raw_result, dict):
                    continue
                result = cast(dict[str, Any], raw_result)
                if result.get("ok") is True and result.get("status") not in {
                    "failed",
                    "ambiguous",
                    "rejected",
                    "submitted",
                    "reserved",
                    "resolved",
                    "pending",
                    "approved",
                    "cancelled",
                }:
                    identifier = str(message.get("tool_call_id", ""))
                    if names.get(identifier) in {
                        "trade_execute",
                        "trade_close_positions",
                        "goal_step_execute",
                    }:
                        outcomes = result.get("results")
                        if result.get("status") != "confirmed" and (
                            not isinstance(outcomes, list)
                            or not outcomes
                            or any(
                                not isinstance(item, dict)
                                or cast(dict[str, Any], item).get("status") != "confirmed"
                                for item in cast(list[Any], outcomes)
                            )
                        ):
                            continue
                    if names.get(identifier) not in {"task_step_update", "task_control"}:
                        successful.add(identifier)
        if not set(request.evidence_call_ids).issubset(successful):
            raise LonoraError("task_step_evidence_invalid", 409)
    step.state, step.evidence_call_ids = request.state, request.evidence_call_ids
    save_task(session, row, state)
    return row


async def request_task_attention(session: AsyncSession, run: RunRow, reason: str) -> None:
    """Keep unfinished work resumable and visible instead of failing its Run.

    The loop hands the owner its best held answer as a pending question; this
    projects that wait on the Task without completing or failing it. The Run's
    checkpoint is unchanged, so the owner's reply resumes the same work.
    """
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
        raise LonoraError("task_run_mismatch", 409)
    state = task_state(row)
    if state.status in {"paused", "completed", "failed", "cancelled"} or state.control_requested:
        return
    if (state.status, state.phase, state.waiting_reason) == (
        "waiting",
        "needs_attention",
        OWNER_ATTENTION,
    ):
        return
    state.status, state.phase, state.waiting_reason = "waiting", "needs_attention", OWNER_ATTENTION
    save_task(session, row, state)
    emit(
        session,
        row.owner_id,
        "task.attention_required",
        agent_id=row.agent_id,
        thread_id=state.origin_thread_id,
        run_id=run.id,
        payload={"id": row.id, "version": row.version, "reason": reason},
    )


async def report_task_degraded(
    session: AsyncSession, run: RunRow, reason: str, code: str, since: str | None
) -> None:
    """Tell the owner that continuous work is retrying through an outage.

    Nothing about the Task changes: it is not held and its Run keeps retrying
    the same checkpoint. One notification per outage (``since`` is when the
    failure streak began); the attention projection drops it once the work has
    recovered or stopped.
    """
    identifier = run.model_metadata.get("task_id")
    if not identifier:
        return
    row = await session.get(TicketRow, identifier)
    if (
        row is None
        or row.agent_id != run.agent_id
        or row.thread_id != run.thread_id
        or not row.state.get("task")
    ):
        return
    state = task_state(row)
    if state.status in {"paused", "completed", "failed", "cancelled"} or state.control_requested:
        return
    emit(
        session,
        row.owner_id,
        "task.degraded",
        agent_id=row.agent_id,
        thread_id=state.origin_thread_id,
        run_id=run.id,
        payload={
            "id": row.id,
            "run_id": run.id,
            "reason": reason,
            "code": code,
            "transition_id": since or code,
        },
    )


async def require_completed_task_steps(session: AsyncSession, run: RunRow) -> None:
    identifier = run.model_metadata.get("task_id")
    if not identifier:
        return
    row = await session.get(TicketRow, identifier, with_for_update=True)
    if row is None or row.agent_id != run.agent_id or row.thread_id != run.thread_id:
        raise LonoraError("task_run_mismatch", 409)
    state = task_state(row)
    if is_continuous_task(state, run):
        raise LonoraError("task_wait_required", 409)
    if any(step.state not in {"completed", "skipped"} for step in state.steps):
        raise LonoraError("task_steps_incomplete", 409)


async def cancel_task_approvals(session: AsyncSession, run_id: str) -> None:
    from .trade_approvals import approval_event

    rows = await session.scalars(
        select(TradeApprovalRow).where(
            TradeApprovalRow.run_id == run_id,
            TradeApprovalRow.status.in_(["pending", "approved"]),
        )
    )
    for approval in rows:
        approval.status = "cancelled"
        approval.updated_at = utcnow()
        approval_event(session, approval)
