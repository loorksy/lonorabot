"""7.1.5: "The owner's 'What is running' view lists every workspace process with the agent
that started it. One tap stops one process, and one tap stops all of them." """

import json
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
from lonora_db.client import Database
from lonora_db.schema import WorkspaceStopRow
from lonora_db.workspace_running import record_listing, request_stop, running_view
from lonora_gateway import runtime as gateway_runtime
from lonora_gateway.service import Gateway
from lonora_workspace.client import WorkspaceClient
from sqlalchemy import select
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]
SECRET = "sk-live-" + "7" * 32
# A secret long enough that the supervisor's 4096-byte cut of a command line ends inside it.
LONG = "tok-" + "Lq9" * 1400
# An agent's CLI token a script put on its own command line (7.3.3, 7.2.6).
CLI_TOKEN = "lnr_" + "Tk7" * 15


def now() -> datetime:
    return datetime.now(UTC)


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
            now(),
        )
    async with db.sessions() as session:
        view = await running_view(session, owner)
    assert [item["pid"] for item in view["processes"]] == [101, 102]
    first = view["processes"][0]
    assert first["agent_id"] == agent and first["agent_name"]
    assert first["command"] == "python bot.py" and not first["stopping"]
    assert first["started_at"].startswith("2023-11-14T")
    assert len(view["processes"][1]["command"]) == 300
    assert view["listed_at"] and not view["stopping_all"] and not view["stale"]
    assert "ppid" not in first and "pid" in first


@pytest.mark.asyncio
async def test_an_older_listing_never_replaces_a_newer_one(task_db: Fixture) -> None:
    db, owner, agent, _ = task_db
    async with db.sessions() as session, session.begin():
        await record_listing(session, owner, [process(201, agent, "new")], now())
        await record_listing(
            session, owner, [process(200, agent, "old")], now() - timedelta(seconds=5)
        )
    async with db.sessions() as session:
        view = await running_view(session, owner)
    assert [item["command"] for item in view["processes"]] == ["new"]


@pytest.mark.asyncio
async def test_an_out_of_date_listing_is_said_and_takes_no_stop(task_db: Fixture) -> None:
    db, owner, agent, _ = task_db
    async with db.sessions() as session, session.begin():
        with pytest.raises(TimeoutError):
            await request_stop(session, owner)
        await record_listing(
            session, owner, [process(101, agent, "python bot.py")], now() - timedelta(minutes=5)
        )
    async with db.sessions() as session, session.begin():
        assert (await running_view(session, owner))["stale"]
        with pytest.raises(TimeoutError):
            await request_stop(session, owner, 101, agent)


@pytest.mark.asyncio
async def test_a_stop_needs_both_the_process_and_its_agent(task_db: Fixture) -> None:
    db, owner, agent, _ = task_db
    async with db.sessions() as session, session.begin():
        await record_listing(session, owner, [process(101, agent, "python bot.py")], now())
        with pytest.raises(ValueError):
            await request_stop(session, owner, 101, None)
        with pytest.raises(LookupError):
            await request_stop(session, owner, 101, "00000000-0000-4000-8000-000000000000")
        await request_stop(session, owner, 101, agent)
    async with db.sessions() as session:
        view = await running_view(session, owner)
    assert view["processes"][0]["stopping"] and not view["stopping_all"]


class Supervisor:
    """The supervisor's process routes, behind the real client (which scans every answer)."""

    def __init__(self, agent: str) -> None:
        self.agent = agent
        self.stopped: list[tuple[int, str]] = []
        self.stopped_all: list[str] = []
        self.listing = [
            process(101, agent, "python bot.py --key " + SECRET),
            process(102, agent, "curl -H 'Authorization: Bearer " + CLI_TOKEN + "' x"),
            process(103, agent, ("bot --token " + LONG)[:4096]),
        ]

    def handle(self, request: httpx.Request) -> httpx.Response:
        body: dict[str, Any] = json.loads(request.content or b"{}")
        if request.url.path == "/v1/processes":
            listing = {"boot_id": "b", "jobs": [], "processes": list(self.listing)}
            return httpx.Response(200, json=listing)
        if request.url.path == "/v1/processes/stop":
            self.stopped.append((body["pid"], body["agent_id"]))
            self.listing = [item for item in self.listing if item["pid"] != body["pid"]]
            return httpx.Response(200, json={"boot_id": "b", "stopped": True})
        self.stopped_all.append(body["agent_id"])
        self.listing = [item for item in self.listing if item["agent_id"] != body["agent_id"]]
        return httpx.Response(200, json={"boot_id": "b", "stopped": 1})


@pytest.mark.asyncio
async def test_one_tap_stops_one_process_and_one_tap_stops_all(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, _ = task_db
    supervisor = Supervisor(agent)
    workspace = WorkspaceClient(transport=httpx.MockTransport(supervisor.handle))
    monkeypatch.setattr(gateway_runtime, "WORKSPACE", workspace)

    class Secrets:
        async def scanned_values(self) -> dict[str, str]:
            return {"BROKER_KEY": SECRET, "LONG_TOKEN": LONG}

    class Tokens:
        async def values(self) -> list[str]:
            return [CLI_TOKEN]

    service: Any = SimpleNamespace(
        owner_id=owner, secrets=Secrets(), given=None, cli_tokens=Tokens()
    )
    gateway: Any = SimpleNamespace(db=db)

    async def workspace_scan(each: Any) -> Any:
        return await Gateway.workspace_scan(gateway, each)

    async def record_running(each: Any) -> None:
        await Gateway.record_running(gateway, each)

    gateway.workspace_scan, gateway.record_running = workspace_scan, record_running

    # The listing the owner sees passes the owner's secret scan (7.2.6).
    await Gateway.record_running(gateway, service)
    async with db.sessions() as session:
        listed = (await running_view(session, owner))["processes"]
    assert listed[0]["command"] == "python bot.py --key [secret:BROKER_KEY]"
    assert all(SECRET not in item["command"] for item in listed)
    # The same scan as the tools' (terminal.owner_scan): agents' CLI tokens too.
    assert listed[1]["command"] == "curl -H 'Authorization: Bearer [secret:LONORA_AGENT_TOKEN]' x"
    # A secret the supervisor's cut ended inside is replaced as well, never shown in part.
    assert listed[2]["command"] == "bot --token [secret:LONG_TOKEN]"
    assert all(LONG[:16] not in item["command"] for item in listed)

    async with db.sessions() as session, session.begin():
        await request_stop(session, owner, 101, agent)
    await Gateway.carry_out_stops(gateway, service)
    assert supervisor.stopped == [(101, agent)] and not supervisor.stopped_all
    async with db.sessions() as session:
        view = await running_view(session, owner)
    assert [item["pid"] for item in view["processes"]] == [102, 103]

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


def test_a_stop_names_a_real_pid() -> None:
    from lonora_api.routes.workspace_running import StopOne
    from pydantic import ValidationError

    assert StopOne.model_validate({"pid": 4_194_304, "agent_id": "a"}).pid == 4_194_304
    for pid in (0, 4_194_305, 2**31):
        with pytest.raises(ValidationError):
            StopOne.model_validate({"pid": pid, "agent_id": "a"})
