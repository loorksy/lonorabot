from datetime import UTC, datetime, timedelta
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.routines import RoutineCreate
from lonora_contracts.runs import RunRequest
from lonora_core.cron import next_occurrence
from lonora_core.user_error import LonoraError
from sqlalchemy import ColumnElement, Select, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .runs import create_run
from .schema import AgentRow, RoutineRow, ThreadRow
from .transactions import owned_agent


def next_run(request: RoutineCreate, after: datetime) -> datetime:
    if request.run_at is not None:
        return request.run_at
    if request.cron:
        return next_occurrence(request.cron, request.timezone, after)
    return after + timedelta(seconds=request.interval_seconds or 60)


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


async def enqueue_routine(session: AsyncSession, row: RoutineRow, now: datetime) -> bool:
    await create_run(
        session,
        row.owner_id,
        RunRequest(
            thread_id=row.thread_id,
            agent_id=row.agent_id,
            trigger="routine",
            prompt=row.prompt,
            metadata={"routine_id": row.id},
        ),
    )
    if row.run_at is not None:
        # A one-shot routine fires once and then stays off until the owner reschedules it.
        row.enabled, row.last_run_at = False, now
        return True
    row.last_run_at = now
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
