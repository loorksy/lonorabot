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
from .runs import create_run, require_lease
from .schema import BoardRow, EventRow, RunRow, TicketRow, TradeApprovalRow
from .threads import create_thread
from .transactions import owned_agent, owned_thread


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
        payload={"id": row.id, "version": row.version, "status": state.status},
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
    if status == "completed" and state.completion_mode == "continuous":
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
            ).model_dump(mode="json")
        },
    )
    if task_id:
        row.id = task_id
    session.add(row)
    await session.flush()
    run = await create_run(
        session,
        owner_id,
        RunRequest(
            thread_id=work.id,
            agent_id=agent_id,
            trigger="tickets",
            prompt=request.title + "\n" + request.description,
            metadata={
                "ticket_id": row.id,
                "task_id": row.id,
                "origin_thread_id": origin_thread_id,
                "lane": "work",
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
        "version": row.version,
        **state.model_dump(mode="json"),
        "status": status,
        "work_thread_id": row.thread_id,
        "phase": phase,
        "waiting_reason": ("approval" if approval_pending else "user_input")
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
        "can_resume": status == "paused" or (status == "failed" and recoverable_failure),
        "can_cancel": status not in {"completed", "cancelled"},
    }


async def control_task(
    session: AsyncSession, owner_id: str, request: TaskControl, *, agent_id: str | None = None
) -> TicketRow:
    row = await get_task(session, owner_id, request.task_id)
    if agent_id and row.agent_id != agent_id:
        raise LonoraError("task_agent_mismatch", 403)
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
        save_task(session, row, state)
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
        if state.status != "paused" or run.status != "waiting_takeover":
            raise LonoraError("task_cannot_resume", 409)
        run.status = "queued"
        state.status, state.phase, state.control_requested = "queued", "queued", None
    elif request.action == "revise":
        revise_task(state, request)
        environment = dict(run.execution_state.get("environment", {}))
        if environment.get("wait"):
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
    save_task(session, row, state)
    return row


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
        state.status = "paused" if pause else "cancelled"
        state.phase, state.control_requested = state.status, None
        save_task(session, row, state)
        return True
    changed = state.status != "running"
    state.status, state.phase = "running", "executing"
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
