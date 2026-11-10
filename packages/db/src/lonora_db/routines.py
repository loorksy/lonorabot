from datetime import UTC, datetime, timedelta
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.routines import RoutineCreate
from lonora_contracts.runs import RunRequest
from lonora_core.cron import next_occurrence
from lonora_core.user_error import LonoraError
from sqlalchemy import Select, select
from sqlalchemy.ext.asyncio import AsyncSession

from .runs import create_run
from .schema import AgentRow, EffectReceiptRow, RoutineRow, ThreadRow, TradingGoalRow
from .trading_goals import owned_goal, planned_step
from .transactions import owned_agent, owned_thread


def next_run(request: RoutineCreate, after: datetime) -> datetime:
    if request.cron:
        return next_occurrence(request.cron, request.timezone, after)
    return after + timedelta(seconds=request.interval_seconds or 60)


def routine_data(row: RoutineRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "thread_id": row.thread_id,
        "prompt": row.prompt,
        "goal_id": row.goal_id,
        "step_id": row.step_id,
        "interval_seconds": row.interval_seconds,
        "cron": row.cron,
        "timezone": row.timezone,
        "enabled": row.enabled,
        "next_run_at": row.next_run_at.isoformat(),
    }


def _taint_key(routine_id: str) -> str:
    return "ui_submit_origin:routine:" + routine_id


async def mark_routine_taint(
    session: AsyncSession, routine_id: str, origin: dict[str, Any]
) -> None:
    """Record that a card's send created this routine; its wake Runs carry the taint."""
    if await session.get(EffectReceiptRow, _taint_key(routine_id)) is None:
        session.add(EffectReceiptRow(key=_taint_key(routine_id), result=origin))


async def routine_taint(session: AsyncSession, routine_id: str) -> dict[str, Any]:
    receipt = await session.get(EffectReceiptRow, _taint_key(routine_id))
    return {"ui_submit_origin": receipt.result} if receipt is not None else {}


async def create_routine(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    request: RoutineCreate,
    resource_id: str | None = None,
) -> RoutineRow:
    await owned_agent(session, owner_id, agent_id)
    if resource_id:
        existing = await session.get(RoutineRow, resource_id)
        if existing:
            return existing
    goal: TradingGoalRow | None = None
    if request.goal_id:
        goal = await owned_goal(session, owner_id, request.goal_id)
        thread = await owned_thread(session, owner_id, goal.thread_id or "", lock=True)
        goal = await owned_goal(session, owner_id, request.goal_id, True)
        if goal.agent_id != agent_id or goal.state.get("status") not in {"active", "waiting"}:
            raise LonoraError("goal_run_mismatch", 409)
        planned_step(goal, request.step_id)
    else:
        thread = ThreadRow(owner_id=owner_id, agent_id=agent_id, title=request.prompt[:80])
        session.add(thread)
        await session.flush()
    row = RoutineRow(
        owner_id=owner_id,
        agent_id=agent_id,
        thread_id=thread.id,
        next_run_at=next_run(request, utcnow()),
        **request.model_dump(),
    )
    if resource_id:
        row.id = resource_id
    session.add(row)
    await session.flush()
    if request.goal_id:
        assert goal is not None
        import copy

        from .trading_goals import update_goal_state

        state = copy.deepcopy(goal.state)
        state["steps"][request.step_id]["routine_id"] = row.id
        state["steps"][request.step_id]["routine_plan_version"] = state.get("plan_version", 1)
        update_goal_state(session, goal, state)
    return row


def due_query(now: datetime) -> Select[RoutineRow]:
    return (
        select(RoutineRow)
        .join(AgentRow, AgentRow.id == RoutineRow.agent_id)
        .where(
            RoutineRow.enabled.is_(True),
            RoutineRow.next_run_at <= now,
            AgentRow.paused.is_(False),
        )
        .order_by(RoutineRow.next_run_at)
    )


async def enqueue_due(session: AsyncSession, limit: int = 30) -> int:
    """Enqueue every due routine in the caller's transaction (one batch, one outcome)."""
    now = utcnow()
    due = list(
        (await session.scalars(due_query(now).limit(limit).with_for_update(skip_locked=True))).all()
    )
    enqueued = 0
    for row in due:
        enqueued += int(await enqueue_routine(session, row, now))
    return enqueued


async def due_routines(session: AsyncSession, limit: int = 30) -> list[tuple[str, str]]:
    """Due routines, skipping any that are backing off or quarantined after failures."""
    from .item_failures import blocked

    rows = await session.execute(
        due_query(utcnow())
        .with_only_columns(RoutineRow.id, RoutineRow.owner_id)
        .where(~blocked("routine", RoutineRow.id))
        .limit(limit)
    )
    return [(identifier, owner_id) for identifier, owner_id in rows]


async def enqueue_one(session: AsyncSession, routine_id: str) -> bool:
    """Enqueue one routine in its own transaction, if it is still due and unclaimed."""
    now = utcnow()
    row = await session.scalar(
        due_query(now)
        .where(RoutineRow.id == routine_id)
        .with_for_update(skip_locked=True, of=RoutineRow)
    )
    return row is not None and await enqueue_routine(session, row, now)


async def disable_routine(session: AsyncSession, routine_id: str) -> bool:
    """Quarantine: a routine that keeps failing stops firing until it is re-enabled."""
    row = await session.get(RoutineRow, routine_id, with_for_update=True)
    if row is not None:
        row.enabled = False
    return True


async def enqueue_routine(session: AsyncSession, row: RoutineRow, now: datetime) -> bool:
    enqueued = False
    if row.goal_id:
        goal = await owned_goal(session, row.owner_id, row.goal_id)
        step_state = goal.state.get("steps", {}).get(row.step_id, {})
        source_version = (
            step_state.get("target_review_plan_version")
            if step_state.get("target_review_id") == row.id
            else step_state.get("routine_plan_version")
            if step_state.get("routine_id") == row.id
            else None
        )
        if (
            source_version is not None
            and source_version != goal.state.get("plan_version", 1)
            or row.step_id not in goal.state.get("steps", {})
        ):
            row.enabled = False
            return False
        target_review = (
            goal.state.get("steps", {}).get(row.step_id, {}).get("target_review_id") == row.id
        )
        if target_review and (
            goal.state.get("code") != "goal_target_pending"
            or goal.state.get("current_step") != row.step_id
            or goal.state.get("status") in {"completed", "cancelled"}
        ):
            row.enabled = False
            return False
    try:
        await create_run(
            session,
            row.owner_id,
            RunRequest(
                thread_id=row.thread_id,
                agent_id=row.agent_id,
                trigger="routine",
                prompt=row.prompt,
                metadata={
                    "routine_id": row.id,
                    **({"goal_id": row.goal_id, "step_id": row.step_id} if row.goal_id else {}),
                    **(await routine_taint(session, row.id)),
                },
            ),
        )
        enqueued = True
    except LonoraError as error:
        if error.code not in {
            "goal_not_active",
            "goal_step_unavailable",
            "goal_step_not_found",
        }:
            raise
    request = RoutineCreate(
        prompt=row.prompt,
        interval_seconds=row.interval_seconds,
        cron=row.cron,
        timezone=row.timezone,
        enabled=row.enabled,
    )
    previous = row.next_run_at if row.next_run_at.tzinfo else row.next_run_at.replace(tzinfo=UTC)
    candidate = next_run(request, previous)
    # Collapse missed schedules into one wake; never replay a burst after downtime.
    row.next_run_at = candidate if candidate > now else next_run(request, now)
    row.last_run_at = now
    return enqueued


async def owned_routine(session: AsyncSession, owner_id: str, routine_id: str) -> RoutineRow:
    row = await session.scalar(
        select(RoutineRow)
        .where(RoutineRow.owner_id == owner_id, RoutineRow.id == routine_id)
        .with_for_update()
    )
    if row is None:
        raise LonoraError("routine_not_found", 404)
    return row
