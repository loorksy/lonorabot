from datetime import UTC, datetime, timedelta
from typing import Any

from lonora_contracts.domain import ThreadCreate, utcnow
from lonora_contracts.routines import RoutineCreate
from lonora_contracts.runs import RunRequest
from lonora_core.cron import next_occurrence
from lonora_core.user_error import LonoraError
from sqlalchemy import ColumnElement, Select, exists, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .runs import create_run
from .schema import AgentRow, RoutineRow, RunRow
from .threads import background_origin, create_thread
from .transactions import owned_agent


def next_run(request: RoutineCreate, after: datetime) -> datetime:
    if request.run_at is not None:
        return request.run_at
    if request.cron:
        return next_occurrence(request.cron, request.timezone, after)
    return after + timedelta(seconds=request.interval_seconds or 60)


# Counting a cron collapse stops here: after months of downtime a minute-by-minute
# schedule would otherwise hold the routine's transaction for seconds.
MISSED_COUNT_CAP = 1000


def missed_occurrences(request: RoutineCreate, due: datetime, now: datetime) -> int:
    """The occurrences after ``due`` up to ``now``: the collapse folds them into one wake."""
    if request.run_at is not None:
        return 0
    if not request.cron:
        elapsed = (now - due).total_seconds() // (request.interval_seconds or 60)
        return min(int(elapsed), MISSED_COUNT_CAP)
    count, at = 0, next_run(request, due)
    while at <= now and count < MISSED_COUNT_CAP:
        count, at = count + 1, next_run(request, at)
    return count


def routine_data(row: RoutineRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "thread_id": row.thread_id,
        "title": row.title,
        "prompt": row.prompt,
        "interval_seconds": row.interval_seconds,
        "cron": row.cron,
        "run_at": row.run_at.isoformat() if row.run_at else None,
        "timezone": row.timezone,
        "enabled": row.enabled,
        "next_run_at": row.next_run_at.isoformat(),
        "last_run_at": row.last_run_at.isoformat() if row.last_run_at else None,
    }


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
    # The routine's hidden work thread is its memory; its results go to the Agent's own
    # conversation, never into a chat of their own (VISION 11.6).
    thread = await create_thread(
        session,
        owner_id,
        ThreadCreate(agent_id=agent_id, title=request.prompt[:80]),
        purpose="work",
    )
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
    return row


def not_fired_one_shot() -> ColumnElement[bool]:
    """A one-shot that already fired never fires again until its run_at is changed, whoever
    switches it back on (owner, the agent's routine_toggle, a supervisor)."""
    return or_(RoutineRow.run_at.is_(None), RoutineRow.last_run_at.is_(None))


def due_query(now: datetime) -> Select[RoutineRow]:
    return (
        select(RoutineRow)
        .join(AgentRow, AgentRow.id == RoutineRow.agent_id)
        .where(
            RoutineRow.enabled.is_(True),
            RoutineRow.next_run_at <= now,
            AgentRow.paused.is_(False),
            not_fired_one_shot(),
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


def mark_routine_started(run: RunRow, now: datetime) -> None:
    """A routine Run's first ``running`` transition, recorded once (``started_at``): its late
    sentence names this start on every context head the Run builds, so a later wake repeats
    the same sentence or none."""
    if run.trigger == "routine" and "started_at" not in run.model_metadata:
        run.model_metadata = {**run.model_metadata, "started_at": now.isoformat()}


async def earlier_run_unfinished(session: AsyncSession, row: RoutineRow) -> bool:
    """A run of this routine in its work thread is queued (a retry backoff included),
    leased or running. One waiting for the owner's answer does not hold the schedule."""
    return bool(
        await session.scalar(
            select(
                exists().where(
                    RunRow.thread_id == row.thread_id,
                    RunRow.trigger == "routine",
                    RunRow.model_metadata["routine_id"].as_string() == row.id,
                    RunRow.status.in_(("queued", "leased", "running")),
                )
            )
        )
    )


async def enqueue_routine(session: AsyncSession, row: RoutineRow, now: datetime) -> bool:
    """Fire one due routine; False when its earlier run is unfinished and the tick is skipped.

    A skipped tick creates no run: the schedule advances as after a run, and the skipped
    occurrences are counted. The next run carries, in server-only metadata, when it was
    due (``scheduled_for``), the later occurrences folded into it (``missed_occurrences``)
    and the occurrences skipped before it (``skipped_occurrences``). A one-shot always fires.
    """
    due = row.next_run_at if row.next_run_at.tzinfo else row.next_run_at.replace(tzinfo=UTC)
    missed = 0
    if row.run_at is None:
        request = RoutineCreate(
            prompt=row.prompt,
            interval_seconds=row.interval_seconds,
            cron=row.cron,
            timezone=row.timezone,
            enabled=row.enabled,
        )
        missed = missed_occurrences(request, due, now)
        candidate = next_run(request, due)
        # Collapse missed schedules into one wake; never replay a burst after downtime.
        row.next_run_at = candidate if candidate > now else next_run(request, now)
        if await earlier_run_unfinished(session, row):
            # No pile of runs behind one still working (11.5); not a cap (P1): the
            # routine fires on its schedule once the earlier run has ended.
            row.skipped_occurrences += 1 + missed
            return False
    run = await create_run(
        session,
        row.owner_id,
        RunRequest(
            thread_id=row.thread_id,
            agent_id=row.agent_id,
            trigger="routine",
            prompt=row.prompt,
            metadata={
                "routine_id": row.id,
                **await background_origin(session, row.owner_id, row.agent_id, row.thread_id),
            },
        ),
    )
    run.model_metadata = {
        **run.model_metadata,
        "scheduled_for": due.isoformat(),
        "missed_occurrences": missed,
        "skipped_occurrences": row.skipped_occurrences,
    }
    row.skipped_occurrences, row.last_run_at = 0, now
    if row.run_at is not None:
        # A one-shot routine fires once and then stays off until the owner reschedules it.
        row.enabled = False
    return True


async def owned_routine(session: AsyncSession, owner_id: str, routine_id: str) -> RoutineRow:
    row = await session.scalar(
        select(RoutineRow)
        .where(RoutineRow.owner_id == owner_id, RoutineRow.id == routine_id)
        .with_for_update()
    )
    if row is None:
        raise LonoraError("routine_not_found", 404)
    return row
