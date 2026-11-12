"""What is running in the owner's workspace (mandate 7.1.5): every process of the owner's
agents with the agent that started it, and the owner's stop and stop-all requests. Only
the Gateway reaches the workspace, so it writes the listing and carries out the stops."""

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentRow, WorkspaceRunningRow, WorkspaceStopRow

COMMAND_SHOWN = 300


def utcnow() -> datetime:
    return datetime.now(UTC)


async def owner_agents(session: AsyncSession, owner_id: str) -> dict[str, str]:
    rows = await session.execute(
        select(AgentRow.id, AgentRow.name).where(AgentRow.owner_id == owner_id)
    )
    return {agent_id: name for agent_id, name in rows.all()}


async def record_listing(
    session: AsyncSession, owner_id: str, processes: list[dict[str, Any]]
) -> None:
    """Keep the owner's agents' processes from a scanned supervisor listing."""
    agents = await owner_agents(session, owner_id)
    kept = [
        {
            "pid": int(item["pid"]),
            "ppid": int(item.get("ppid") or 0),
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
        session.add(WorkspaceRunningRow(owner_id=owner_id, processes=kept, listed_at=utcnow()))
    else:
        row.processes, row.listed_at = kept, utcnow()


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
        "listed_at": row.listed_at.isoformat() if row else None,
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
    stop = WorkspaceStopRow(
        id=str(uuid.uuid4()), owner_id=owner_id, pid=pid, agent_id=agent_id, requested_at=utcnow()
    )
    session.add(stop)
    return stop.id


async def pending_stops(session: AsyncSession, owner_id: str) -> list[WorkspaceStopRow]:
    return list(
        (
            await session.scalars(
                select(WorkspaceStopRow)
                .where(WorkspaceStopRow.owner_id == owner_id, WorkspaceStopRow.done_at.is_(None))
                .order_by(WorkspaceStopRow.requested_at)
                .with_for_update(skip_locked=True)
            )
        ).all()
    )
