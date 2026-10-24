"""Wait/wake for existing Task/Run identities; driven by the resident scheduler."""

from datetime import timedelta
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.runs import Lease
from lonora_contracts.tasks import TaskWait
from lonora_core.user_error import LonoraError
from lonora_session.idempotency import request_hash, stable_id
from sqlalchemy import and_, exists, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .client import Database
from .events import emit
from .runs import locked_run_thread
from .schema import BrokerSessionRow, EffectReceiptRow, MarketWatchRow, RunRow, ThreadRow, TicketRow
from .tasks import save_task, task_state


async def prepare_wait(
    session: AsyncSession, lease: Lease, request: TaskWait, call_id: str
) -> dict[str, Any]:
    run, thread = await locked_run_thread(session, lease)
    task = await session.get(TicketRow, run.model_metadata.get("task_id", ""), with_for_update=True)
    if task is None or task.agent_id != run.agent_id or task.thread_id != run.thread_id:
        raise LonoraError("task_run_mismatch", 409)
    state = task_state(task)
    if state.control_requested or state.status in {"cancelled", "paused", "failed", "completed"}:
        raise LonoraError("task_not_running", 409)
    if request.kind == "watch":
        source = await session.get(MarketWatchRow, request.source_id)
        if (
            source is None
            or source.owner_id != thread.owner_id
            or source.agent_id != run.agent_id
            or source.thread_id != run.thread_id
            or source.payload.get("goal_id")
            or not source.payload.get("enabled", True)
        ):
            raise LonoraError("task_wait_source_invalid", 409)
    elif request.kind == "broker_recovery":
        from .agent_binding import agent_binding, assert_market_binding

        source = await session.get(BrokerSessionRow, request.source_id)
        if source is None or source.owner_id != thread.owner_id:
            raise LonoraError("task_wait_source_invalid", 409)
        assert_market_binding(
            await agent_binding(session, thread.owner_id, run.agent_id), source.id
        )
    key = "task-wait:" + stable_id(run.id, call_id)
    receipt = await session.get(EffectReceiptRow, key)
    if receipt:
        wait = dict(receipt.result)
        if wait.get("intent") != request_hash(request.model_dump(mode="json")):
            raise LonoraError("operation_id_conflict", 409)
        if wait.get("resumed"):
            raise LonoraError("task_wait_already_resumed", 409)
    else:
        wait = {
            "kind": request.kind,
            "source_id": request.source_id,
            "task_id": task.id,
            "run_id": run.id,
            "call_id": call_id,
            "created_at": utcnow().isoformat(),
            "intent": request_hash(request.model_dump(mode="json")),
            "due_at": (utcnow() + timedelta(seconds=request.seconds)).isoformat()
            if request.kind == "timer"
            else None,
        }
        session.add(EffectReceiptRow(key=key, result=wait))
    state.status, state.phase, state.waiting_reason = (
        "waiting",
        "waiting",
        "external_" + request.kind,
    )
    save_task(session, task, state)
    return wait


async def wake_waiting_run(
    session: AsyncSession,
    run_id: str,
    *,
    kind: str,
    source_id: str | None,
    observation: str,
    expected_call_id: str,
) -> bool:
    initial = await session.get(RunRow, run_id)
    if initial is None:
        return False
    thread = await session.get(
        ThreadRow, initial.thread_id, with_for_update=True, populate_existing=True
    )
    run = await session.get(RunRow, run_id, with_for_update=True, populate_existing=True)
    if run is None or thread is None or run.status != "waiting_takeover":
        return False
    environment = dict(run.execution_state.get("environment", {}))
    wait = environment.get("wait", {})
    if (
        wait.get("kind") != kind
        or wait.get("source_id") != source_id
        or wait.get("call_id") != expected_call_id
    ):
        return False
    task = await session.get(TicketRow, run.model_metadata.get("task_id", ""), with_for_update=True)
    if task is None or task.agent_id != run.agent_id or task.thread_id != run.thread_id:
        return False
    state = task_state(task)
    if state.status != "waiting" or state.control_requested:
        return False
    receipt_key = "task-wake:" + stable_id(run.id, str(wait["call_id"]) + ":" + observation)
    if await session.get(EffectReceiptRow, receipt_key):
        return False
    if kind == "watch":
        consumed = "task-watch-observation:" + str(source_id) + ":" + observation
        if await session.get(EffectReceiptRow, consumed):
            return False
        session.add(EffectReceiptRow(key=consumed, result={"run_id": run.id, "task_id": task.id}))
    session.add(EffectReceiptRow(key=receipt_key, result={"run_id": run.id, "task_id": task.id}))
    admission = await session.get(
        EffectReceiptRow, "task-wait:" + stable_id(run.id, str(wait["call_id"]))
    )
    if admission:
        admission.result = {**admission.result, "resumed": True}
    environment.pop("wait", None)
    environment.pop("wait_update", None)
    environment["last_wake"] = {
        "kind": kind,
        "source_id": source_id,
        "observation": observation,
        "at": utcnow().isoformat(),
    }
    environment["phase"] = "revalidating"
    run.execution_state = {
        # A real external wake starts a fresh bounded review. Worker retries
        # and restarts alone must not replenish this compute budget.
        **{
            key: value
            for key, value in run.execution_state.items()
            if key not in {"task_continuation", "continuous_stop_gate"}
        },
        "environment": environment,
        "prior_attempt_rounds": int(run.execution_state.get("prior_attempt_rounds", 0))
        + int(run.execution_state.get("rounds", 0)),
        "rounds": 0,
    }
    run.status, run.lease_expires_at = "queued", None
    run.updated_at = utcnow()
    state.status, state.phase, state.waiting_reason = "queued", "revalidating", None
    save_task(session, task, state)
    emit(
        session,
        thread.owner_id,
        "task.woken",
        thread_id=state.origin_thread_id,
        agent_id=run.agent_id,
        run_id=run.id,
        payload={"id": task.id, "source_kind": kind, "source_id": source_id},
    )
    return True


async def resume_ready_waits(db: Database) -> int:
    wait = RunRow.execution_state["environment"]["wait"]
    source_id = wait["source_id"].as_string()
    observed = MarketWatchRow.state["last_triggered"].as_string()
    consumed = exists(
        select(EffectReceiptRow.key)
        .where(
            EffectReceiptRow.key
            == literal("task-watch-observation:") + MarketWatchRow.id + literal(":") + observed
        )
        .correlate(MarketWatchRow)
    )
    watch_ready = exists(
        select(MarketWatchRow.id)
        .where(
            MarketWatchRow.id == source_id,
            MarketWatchRow.agent_id == RunRow.agent_id,
            MarketWatchRow.thread_id == RunRow.thread_id,
            observed.is_not(None),
            ~consumed,
        )
        .correlate(RunRow)
    )
    broker_ready = exists(
        select(BrokerSessionRow.id)
        .where(
            BrokerSessionRow.id == source_id,
            BrokerSessionRow.state["broker_recovery"]["status"].as_string() == "connected",
            BrokerSessionRow.state["broker_recovery"]["observed_at"].as_string()
            >= wait["created_at"].as_string(),
        )
        .correlate(RunRow)
    )
    ready_source = or_(
        and_(
            wait["kind"].as_string() == "timer", wait["due_at"].as_string() <= utcnow().isoformat()
        ),
        and_(wait["kind"].as_string() == "watch", watch_ready),
        and_(wait["kind"].as_string() == "broker_recovery", broker_ready),
    )
    async with db.sessions() as session:
        rows = list(
            await session.scalars(
                select(RunRow)
                .join(TicketRow, TicketRow.id == RunRow.model_metadata["task_id"].as_string())
                .where(
                    RunRow.status == "waiting_takeover",
                    TicketRow.state["task"]["status"].as_string() == "waiting",
                    ready_source,
                )
                .order_by(RunRow.updated_at)
                .limit(50)
            )
        )
    changed = 0
    for candidate in rows:
        wait = candidate.execution_state["environment"]["wait"]
        kind, source_id = wait["kind"], wait.get("source_id")
        async with db.sessions() as session, session.begin():
            thread = await session.get(ThreadRow, candidate.thread_id)
            if thread is None:
                continue
            ready, observation = False, ""
            if kind == "timer":
                ready, observation = wait["due_at"] <= utcnow().isoformat(), wait["due_at"]
            elif kind == "watch":
                source = await session.get(MarketWatchRow, source_id)
                if (
                    source
                    and source.owner_id == thread.owner_id
                    and source.agent_id == candidate.agent_id
                    and source.thread_id == candidate.thread_id
                ):
                    observed = source.state.get("last_triggered")
                    ready = bool(observed and observed >= source.created_at.isoformat())
                    observation = str(observed or "")
            elif kind == "broker_recovery":
                source = await session.get(BrokerSessionRow, source_id)
                recovery: dict[str, Any] = (
                    source.state.get("broker_recovery", {})
                    if source and source.owner_id == thread.owner_id
                    else {}
                )
                ready = (
                    recovery.get("status") == "connected"
                    and recovery.get("observed_at", "") >= wait["created_at"]
                )
                observation = str(recovery.get("observed_at", ""))
            if ready:
                changed += int(
                    await wake_waiting_run(
                        session,
                        candidate.id,
                        kind=kind,
                        source_id=source_id,
                        observation=observation,
                        expected_call_id=wait["call_id"],
                    )
                )
    return changed
