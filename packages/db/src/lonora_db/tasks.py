"""Task lifecycle backed by the existing ticket, run and event ledger."""

from typing import Any

from lonora_contracts.domain import ThreadCreate, utcnow
from lonora_contracts.runs import Lease, RunRequest
from lonora_contracts.tasks import TaskControl, TaskCreate, TaskState
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


def save_task(session: AsyncSession, row: TicketRow, state: TaskState) -> None:
    row.state = {**row.state, "task": state.model_dump(mode="json")}
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
        session, owner_id, ThreadCreate(agent_id=agent_id, title=request.title)
    )
    row = TicketRow(
        owner_id=owner_id,
        agent_id=agent_id,
        thread_id=work.id,
        payload={
            "board_id": board.id,
            "title": request.title,
            "description": request.description,
            "status": "working",
        },
        state={
            "task": TaskState(origin_thread_id=origin_thread_id, steps=request.steps).model_dump(
                mode="json"
            )
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
    if not active and runs and runs[0].status in {"completed", "failed", "cancelled"}:
        status = runs[0].status
    if active and state.status not in {"paused", "cancelled"}:
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
        if any(tool["active"] for tool in pending_tools.values()) and active
        else "thinking"
        if active and active.status == "running"
        else status
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
        "active_tools": [tool["name"] for tool in pending_tools.values() if tool["active"]],
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
        "can_resume": status == "paused",
        "can_cancel": status not in {"completed", "failed", "cancelled"},
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
        if not request.instruction and request.steps is None:
            raise LonoraError("task_revision_empty", 422)
        if request.steps is not None:
            ids = [step.id for step in request.steps]
            if len(set(ids)) != len(ids):
                raise LonoraError("task_step_duplicate", 422)
            completed = {
                step.id: step for step in state.steps if step.state in {"completed", "skipped"}
            }
            if any(
                next((step for step in request.steps if step.id == key), None) != value
                for key, value in completed.items()
            ):
                raise LonoraError("task_completed_step_immutable", 409)
            state.steps = request.steps
        state.instruction = request.instruction
        state.plan_revision += 1
    else:
        state.control_requested = request.action
        if run.status in {"queued", "waiting_input", "waiting_takeover"}:
            run.status = "waiting_takeover" if request.action == "pause" else "cancelled"
            state.status = "paused" if request.action == "pause" else "cancelled"
            state.phase = state.status
            state.control_requested = None
    save_task(session, row, state)
    return row


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
