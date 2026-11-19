"""What is running in the owner's workspace (mandate 7.1.5): every process of the owner's
agents with the agent that started it, and the owner's stop and stop-all requests. Only
the Gateway reaches the workspace, so it writes the listing and carries out the stops."""

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import delete, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentRow, WorkspaceRunningRow, WorkspaceStopRow

COMMAND_SHOWN = 300
# A listing older than this is shown as out of date, and stops are not taken: the
# Gateway lists the workspace every 10 s while it can reach it.
STALE = timedelta(seconds=60)
KEPT = timedelta(days=7)


def utcnow() -> datetime:
    return datetime.now(UTC)


def aware(moment: datetime) -> datetime:
    """A stored time as UTC: SQLite returns timestamps without their zone."""
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


async def owner_agents(session: AsyncSession, owner_id: str) -> dict[str, str]:
    rows = await session.execute(
        select(AgentRow.id, AgentRow.name).where(AgentRow.owner_id == owner_id)
    )
    return {agent_id: name for agent_id, name in rows.all()}


async def record_listing(
    session: AsyncSession, owner_id: str, processes: list[dict[str, Any]], listed_at: datetime
) -> None:
    """Keep the owner's agents' processes from a scanned supervisor listing asked for at
    `listed_at`; a listing older than the one kept is dropped."""
    agents = await owner_agents(session, owner_id)
    kept = [
        {
            "pid": int(item["pid"]),
            "agent_id": str(item["agent_id"]),
            "command": str(item.get("command") or "")[:COMMAND_SHOWN],
            "started_at": datetime.fromtimestamp(float(item["started_at"]), UTC).isoformat()
            if item.get("started_at") is not None
            else None,
        }
        for item in processes
        if str(item.get("agent_id")) in agents
    ]
    row = await session.get(WorkspaceRunningRow, owner_id, with_for_update=True)
    if row is None:
        session.add(WorkspaceRunningRow(owner_id=owner_id, processes=kept, listed_at=listed_at))
    elif aware(row.listed_at) <= listed_at:
        row.processes, row.listed_at = kept, listed_at


def stale(row: WorkspaceRunningRow | None) -> bool:
    return row is None or aware(row.listed_at) < utcnow() - STALE


async def running_view(session: AsyncSession, owner_id: str) -> dict[str, Any]:
    """The view's data: each process with its agent's name, and what is being stopped."""
    row = await session.get(WorkspaceRunningRow, owner_id)
    agents = await owner_agents(session, owner_id)
    stops = (
        await session.scalars(
            select(WorkspaceStopRow).where(
                WorkspaceStopRow.owner_id == owner_id, WorkspaceStopRow.done_at.is_(None)
            )
        )
    ).all()
    stopping = {(stop.pid, stop.agent_id) for stop in stops if stop.pid is not None}
    processes = [
        {
            **item,
            "agent_name": agents.get(item["agent_id"], ""),
            "stopping": (item["pid"], item["agent_id"]) in stopping,
        }
        for item in (row.processes if row else [])
        if item["agent_id"] in agents
    ]
    return {
        "listed_at": aware(row.listed_at).isoformat() if row else None,
        "stale": stale(row),
        "processes": processes,
        "stopping_all": any(stop.pid is None for stop in stops),
    }


async def request_stop(
    session: AsyncSession, owner_id: str, pid: int | None = None, agent_id: str | None = None
) -> str:
    """One process (pid and the agent it runs as) or, with neither, every process."""
    if (pid is None) != (agent_id is None):
        raise ValueError("workspace_stop_target_invalid")
    if agent_id is not None and agent_id not in await owner_agents(session, owner_id):
        raise LookupError("agent_not_found")
    # A stop is carried out against the workspace as it is now: not while it is not seen.
    if stale(await session.get(WorkspaceRunningRow, owner_id)):
        raise TimeoutError("workspace_unavailable")
    stop = WorkspaceStopRow(
        id=str(uuid.uuid4()), owner_id=owner_id, pid=pid, agent_id=agent_id, requested_at=utcnow()
    )
    session.add(stop)
    return stop.id


async def claim_stops(session: AsyncSession, owner_id: str) -> list[WorkspaceStopRow]:
    """The owner's stops not yet taken, marked done as they are taken, in the caller's
    transaction: each stop is carried out at most once, even by two Gateways or after a
    crash (a stop lost to a crash is tapped again). Rows done a week ago are forgotten."""
    await session.execute(
        delete(WorkspaceStopRow).where(WorkspaceStopRow.done_at < utcnow() - KEPT)
    )
    return list(
        (
            await session.scalars(
                update(WorkspaceStopRow)
                .where(WorkspaceStopRow.owner_id == owner_id, WorkspaceStopRow.done_at.is_(None))
                .values(done_at=utcnow())
                .returning(WorkspaceStopRow)
            )
        ).all()
    )
