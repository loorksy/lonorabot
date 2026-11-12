"""7.1.5: "The owner's 'What is running' view lists every workspace process with the agent
that started it. One tap stops one process, and one tap stops all of them." """

from types import SimpleNamespace
from typing import Any

import pytest
from lonora_db.client import Database
from lonora_db.schema import WorkspaceStopRow
from lonora_db.workspace_running import record_listing, request_stop, running_view
from lonora_gateway import runtime as gateway_runtime
from lonora_gateway.service import Gateway
from sqlalchemy import select
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]


def process(pid: int, agent: str, command: str, ppid: int = 1) -> dict[str, Any]:
    return {
        "pid": pid,
        "ppid": ppid,
        "agent_id": agent,
        "user": "a20000",
        "command": command,
        "started_at": 1_700_000_000.0,
        "state": "S",
    }


@pytest.mark.asyncio
async def test_every_process_is_listed_with_the_agent_that_started_it(task_db: Fixture) -> None:
    db, owner, agent, _ = task_db
    async with db.sessions() as session, session.begin():
        await record_listing(
            session,
            owner,
            [
                process(101, agent, "python bot.py"),
                process(102, agent, "node " + "x" * 400, ppid=101),
                # Another installation's or a deleted agent's process is not the owner's.
                process(103, "00000000-0000-4000-8000-000000000000", "sleep 1"),
            ],
        )
    async with db.sessions() as session:
        view = await running_view(session, owner)
    assert [item["pid"] for item in view["processes"]] == [101, 102]
    first = view["processes"][0]
    assert first["agent_id"] == agent and first["agent_name"]
    assert first["command"] == "python bot.py" and not first["stopping"]
    assert first["started_at"].startswith("2023-11-14T")
    assert len(view["processes"][1]["command"]) == 300
    assert view["listed_at"] and not view["stopping_all"]


@pytest.mark.asyncio
async def test_a_stop_needs_both_the_process_and_its_agent(task_db: Fixture) -> None:
    db, owner, agent, _ = task_db
    async with db.sessions() as session, session.begin():
        with pytest.raises(ValueError):
            await request_stop(session, owner, 101, None)
        with pytest.raises(LookupError):
            await request_stop(session, owner, 101, "00000000-0000-4000-8000-000000000000")
        await request_stop(session, owner, 101, agent)
        await record_listing(session, owner, [process(101, agent, "python bot.py")])
    async with db.sessions() as session:
        view = await running_view(session, owner)
    assert view["processes"][0]["stopping"] and not view["stopping_all"]


class Supervisor:
    def __init__(self, agent: str) -> None:
        self.agent = agent
        self.stopped: list[tuple[int, str]] = []
        self.stopped_all: list[str] = []
        self.listing = [process(101, agent, "python bot.py"), process(102, agent, "sleep 9")]

    def present(self) -> bool:
        return True

    async def processes(self, scan: Any) -> dict[str, Any]:
        return {"boot_id": "b", "jobs": [], "processes": list(self.listing)}

    async def stop(self, scan: Any, pid: int, agent_id: str) -> dict[str, Any]:
        self.stopped.append((pid, agent_id))
        self.listing = [item for item in self.listing if item["pid"] != pid]
        return {"stopped": True}

    async def stop_all(self, scan: Any, agent_id: str) -> dict[str, Any]:
        self.stopped_all.append(agent_id)
        self.listing = [item for item in self.listing if item["agent_id"] != agent_id]
        return {"stopped": 1}


@pytest.mark.asyncio
async def test_one_tap_stops_one_process_and_one_tap_stops_all(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, _ = task_db
    supervisor = Supervisor(agent)
    monkeypatch.setattr(gateway_runtime, "WORKSPACE", supervisor)

    class Secrets:
        async def scanned_values(self) -> dict[str, str]:
            return {}

    service: Any = SimpleNamespace(owner_id=owner, secrets=Secrets(), given=None)
    gateway: Any = SimpleNamespace(db=db)

    async def workspace_scan(each: Any) -> Any:
        return await Gateway.workspace_scan(gateway, each)

    async def record_running(each: Any) -> None:
        await Gateway.record_running(gateway, each)

    gateway.workspace_scan, gateway.record_running = workspace_scan, record_running

    async with db.sessions() as session, session.begin():
        await request_stop(session, owner, 101, agent)
    await Gateway.carry_out_stops(gateway, service)
    assert supervisor.stopped == [(101, agent)] and not supervisor.stopped_all
    async with db.sessions() as session:
        view = await running_view(session, owner)
    assert [item["pid"] for item in view["processes"]] == [102]

    async with db.sessions() as session, session.begin():
        await request_stop(session, owner)
    await Gateway.carry_out_stops(gateway, service)
    assert supervisor.stopped_all == [agent]
    async with db.sessions() as session:
        view = await running_view(session, owner)
        assert view["processes"] == [] and not view["stopping_all"]
        stops = (await session.scalars(select(WorkspaceStopRow))).all()
    assert len(stops) == 2 and all(stop.done_at is not None for stop in stops)
    # Done once: a later tick carries nothing out again.
    await Gateway.carry_out_stops(gateway, service)
    assert supervisor.stopped == [(101, agent)] and supervisor.stopped_all == [agent]
