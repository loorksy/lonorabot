from datetime import UTC, datetime, timedelta
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.routines import RoutineCreate
from lonora_contracts.runs import RunRequest
from lonora_core.cron import next_occurrence
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .runs import create_run
from .schema import AgentRow, RoutineRow, ThreadRow
from .transactions import owned_agent


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
        "interval_seconds": row.interval_seconds,
        "cron": row.cron,
        "timezone": row.timezone,
        "enabled": row.enabled,
        "next_run_at": row.next_run_at.isoformat(),
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


async def enqueue_due(session: AsyncSession, limit: int = 30) -> int:
    now = utcnow()
    due = list(
        (
            await session.scalars(
                select(RoutineRow)
                .join(AgentRow, AgentRow.id == RoutineRow.agent_id)
                .where(
                    RoutineRow.enabled.is_(True),
                    RoutineRow.next_run_at <= now,
                    AgentRow.paused.is_(False),
                )
                .order_by(RoutineRow.next_run_at)
                .limit(limit)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
    for row in due:
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
        request = RoutineCreate(
            prompt=row.prompt,
            interval_seconds=row.interval_seconds,
            cron=row.cron,
            timezone=row.timezone,
            enabled=row.enabled,
        )
        previous = (
            row.next_run_at if row.next_run_at.tzinfo else row.next_run_at.replace(tzinfo=UTC)
        )
        candidate = next_run(request, previous)
        # Collapse missed schedules into one wake; never replay a burst after downtime.
        row.next_run_at = candidate if candidate > now else next_run(request, now)
        row.last_run_at = now
    return len(due)


async def owned_routine(session: AsyncSession, owner_id: str, routine_id: str) -> RoutineRow:
    row = await session.scalar(
        select(RoutineRow)
        .where(RoutineRow.owner_id == owner_id, RoutineRow.id == routine_id)
        .with_for_update()
    )
    if row is None:
        raise LonoraError("routine_not_found", 404)
    return row
