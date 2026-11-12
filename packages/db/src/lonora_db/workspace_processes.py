"""Background processes agents started in the owner's workspace, and the notice that tells
an agent on its next wake which of them ended (mandate 7.1.2)."""

from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .client import Database
from .schema import WorkspaceProcessRow

NOTICE_LIMIT = 10
COMMAND_SHOWN = 160
KEPT = timedelta(days=7)
SETTLE = timedelta(seconds=5)


def utcnow() -> datetime:
    return datetime.now(UTC)


async def started(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    job_id: str,
    boot_id: str,
    pid: int,
    command: str,
) -> None:
    session.add(
        WorkspaceProcessRow(
            id=job_id,
            owner_id=owner_id,
            agent_id=agent_id,
            boot_id=boot_id,
            pid=pid,
            command=command,
        )
    )


def outcome_of(
    row: WorkspaceProcessRow, listing: dict[str, Any], fetched_at: datetime
) -> tuple[str, int | None] | None:
    """How a still-open row ended, from the supervisor's listing; None while it runs. A
    row recorded after the listing was asked for is not in it yet, and is not lost."""
    if listing["boot_id"] != row.boot_id:
        return "restarted", None
    job = next((job for job in listing["jobs"] if job["id"] == row.id), None)
    if job is None:
        started = row.started_at if row.started_at.tzinfo else row.started_at.replace(tzinfo=UTC)
        return ("lost", None) if started < fetched_at - SETTLE else None
    if job["ended_at"] is None:
        return None
    return ("stopped" if job["stopped"] else "exited"), job["exit_code"]


async def reconcile(session: AsyncSession, listing: dict[str, Any], fetched_at: datetime) -> int:
    """Close every open row the listing shows ended (one workspace per installation), and
    forget rows reported more than a week ago. Returns how many closed."""
    await session.execute(
        delete(WorkspaceProcessRow).where(WorkspaceProcessRow.reported_at < utcnow() - KEPT)
    )
    rows = (
        await session.scalars(
            select(WorkspaceProcessRow).where(WorkspaceProcessRow.ended_at.is_(None))
        )
    ).all()
    closed = 0
    for row in rows:
        found = outcome_of(row, listing, fetched_at)
        if found is not None:
            row.outcome, row.exit_code = found
            row.ended_at = utcnow()
            closed += 1
    return closed


def notice(rows: Sequence[WorkspaceProcessRow]) -> str:
    lines: list[str] = []
    for row in rows:
        command = (
            row.command if len(row.command) <= COMMAND_SHOWN else row.command[:COMMAND_SHOWN] + "…"
        )
        if row.outcome == "restarted":
            how = "ended when the workspace restarted"
        elif row.outcome == "lost":
            how = "ended (no exit status is known)"
        elif row.outcome == "stopped":
            how = f"was stopped (exit {row.exit_code})"
        else:
            how = f"exited with code {row.exit_code}"
        lines.append(f"- pid {row.pid} `{command}` {how}.")
    return "Your background workspace processes that ended since your last run:\n" + "\n".join(
        lines
    )


async def ended_notice(db: Database, agent_id: str, run_id: str) -> str:
    """The notice for this agent's ended processes not yet told to an earlier run. Each
    is shown for the whole run that first carries it, and never in a later one."""
    async with db.sessions() as session, session.begin():
        rows = (
            await session.scalars(
                select(WorkspaceProcessRow)
                .where(
                    WorkspaceProcessRow.agent_id == agent_id,
                    WorkspaceProcessRow.ended_at.is_not(None),
                    or_(
                        WorkspaceProcessRow.reported_run_id.is_(None),
                        WorkspaceProcessRow.reported_run_id == run_id,
                    ),
                )
                .order_by(WorkspaceProcessRow.ended_at)
                .with_for_update()
            )
        ).all()
        if not rows:
            return ""
        now = utcnow()
        for row in rows:
            if row.reported_run_id is None:
                row.reported_run_id, row.reported_at = run_id, now
        shown = list(rows[-NOTICE_LIMIT:])
        text = notice(shown)
        if len(rows) > len(shown):
            text += f"\n(and {len(rows) - len(shown)} earlier ones)"
        return text
