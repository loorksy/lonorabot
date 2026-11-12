"""Lonora's lead powers are built in (mandate 3.1.6, 14.3.15): no revoked grant ends them.

Runs the real tools and owner routes against the test database (skipped without
``LONORA_DATABASE_URL``).
"""

import json
import os
from typing import Any
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_core.user_error import LonoraError
from lonora_db.schema import MemoryRow, MessageRow, ThreadRow
from lonora_tools.loader import load_tools

SENTINEL = "leadsentinel"


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Lead reads use PostgreSQL full-text search.")


async def call(context: Any, name: str, **arguments: Any) -> dict[str, Any]:
    result = await load_tools().execute(
        ToolCall(id="call-" + uuid4().hex, name=name, arguments=arguments), context
    )
    json.dumps(result)
    return result


async def refused(context: Any, name: str, **arguments: Any) -> str:
    try:
        await call(context, name, **arguments)
    except LonoraError as error:
        return error.code
    raise AssertionError("expected a refusal from " + name)


async def wake(fixture: Any, agent: dict[str, Any]) -> Any:
    """A Run no owner message started: a routine wake in the agent's own conversation."""
    from lonora_contracts.runs import RunRequest
    from lonora_db.runs import create_run

    thread = await fixture.conversation(agent)
    async with fixture.runtime.db.sessions() as session, session.begin():
        run = await create_run(
            session,
            fixture.owner,
            RunRequest(
                thread_id=thread["id"], agent_id=agent["id"], trigger="routine", prompt="Check"
            ),
        )
        data = {"id": run.id, "agent_id": agent["id"], "thread_id": thread["id"]}
    return await fixture.lease(data)


@pytest.mark.asyncio
async def test_lonora_reads_and_steers_a_team_agent_after_its_grant_is_revoked():
    database()
    from check_streaming import Fixture
    from lonora_db.personal_agent import ensure_personal_agent

    fixture = await Fixture().open()
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await ensure_personal_agent(session, fixture.owner)
            lonora = {"id": row.id, "name": row.name}
        gold, peer = await fixture.agent("Gold"), await fixture.agent("Peer")
        gold_thread = await fixture.conversation(gold)
        async with fixture.runtime.db.sessions() as session, session.begin():
            thread = await session.get(ThreadRow, gold_thread["id"], with_for_update=True)
            assert thread is not None
            session.add(
                MessageRow(
                    thread_id=thread.id,
                    seq=thread.next_seq,
                    role="assistant",
                    agent_id=gold["id"],
                    content=SENTINEL + " skipped the London entry",
                )
            )
            thread.next_seq += 1
            memory = await session.get(MemoryRow, gold["id"])
            assert memory is not None
            memory.content = "# MEMORY.md\n- " + SENTINEL + " spreads widen at the open\n"
        gold_run = await fixture.run(gold, gold_thread)

        # The owner revokes Lonora's default grant over Gold: the lead role remains.
        view = await fixture.request("GET", f"/supervision?agent_id={gold['id']}")
        (default,) = [
            item for item in view["supervised_by"] if item["supervisor"]["id"] == lonora["id"]
        ]
        assert default["created_via"] == "default"
        await fixture.request("POST", f"/supervision/{default['id']}/revoke")
        view = await fixture.request("GET", f"/supervision?agent_id={gold['id']}")
        assert view["supervised_by"] == []

        lead = await wake(fixture, lonora)
        found = await call(lead, "session_search", query=SENTINEL)
        assert {item["thread_id"] for item in found["results"]} == {gold_thread["id"]}
        assert all(item["untrusted"] is True for item in found["results"])
        page = await call(lead, "session_search", thread_id=gold_thread["id"])
        assert page["thread"]["supervised_agent"]["id"] == gold["id"]
        literal = await call(lead, "search_internal", query=SENTINEL)
        assert [item["agent_id"] for item in literal["memory"]] == [gold["id"]]
        run = await call(lead, "subagent_inspect", run_id=gold_run["id"])
        assert run["id"] == gold_run["id"] and run["untrusted"] is True
        memory_page = await call(lead, "agent_inspect", agent_id=gold["id"], section="memory")
        assert SENTINEL in memory_page["memory"]
        overview = await call(lead, "agent_inspect", agent_id="Gold")
        assert overview["agent"]["id"] == gold["id"] and lonora["name"] in overview["supervised_by"]
        directory = {item["id"]: item for item in (await call(lead, "list_agents"))["agents"]}
        assert directory[gold["id"]]["you_supervise"] is True
        # Lonora steers it too: a pause and a resume of its own pause, with no grant.
        paused = await call(lead, "agent_control", agent_id=gold["id"], action="pause")
        assert paused["changed"] is True and paused["paused"] is True
        resumed = await call(lead, "agent_control", agent_id=gold["id"], action="resume")
        assert resumed["changed"] is True and resumed["paused"] is False

        # A team agent holds no lead role: Gold's work stays private to it.
        team = await wake(fixture, peer)
        for arguments in (
            {"thread_id": gold_thread["id"]},
            {"query": "x", "thread_id": gold_thread["id"]},
        ):
            assert await refused(team, "session_search", **arguments) == "thread_not_found"
        assert await refused(team, "subagent_inspect", run_id=gold_run["id"]) == "run_not_found"
        assert await refused(team, "agent_inspect", agent_id=gold["id"]) == "supervision_required"
        assert (
            await refused(team, "agent_control", agent_id=gold["id"], action="pause")
            == "supervision_required"
        )
        assert (await call(team, "session_search", query=SENTINEL))["results"] == []
        assert (await call(team, "search_internal", query=SENTINEL))["memory"] == []
        directory = {item["id"]: item for item in (await call(team, "list_agents"))["agents"]}
        assert directory[gold["id"]]["you_supervise"] is False
        assert directory[lonora["id"]]["supervises_you"] is True
    finally:
        await fixture.close()
