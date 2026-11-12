"""Lonora's lead powers are built in (mandate 3.1.6, 14.3.15): they need no grant.

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
async def test_lonora_reads_and_steers_a_team_agent_with_no_grant():
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


@pytest.mark.asyncio
async def test_lonora_cancels_a_run_switches_to_ask_and_pauses_without_a_card():
    database()
    from check_streaming import Fixture
    from lonora_db.personal_agent import ensure_personal_agent
    from lonora_db.schema import OwnerActionRow, RunRow
    from lonora_db.trading_mode import set_trading_mode, trading_mode
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await ensure_personal_agent(session, fixture.owner)
            lonora = {"id": row.id, "name": row.name}
        gold, peer = await fixture.agent("Gold"), await fixture.agent("Peer")
        gold_run = await fixture.run(gold, await fixture.conversation(gold))
        await fixture.lease(gold_run)
        # An owner message waiting its turn is not the current run: it stays.
        queued = await fixture.run(gold, await fixture.conversation(gold))
        async with fixture.runtime.db.sessions() as session, session.begin():
            await set_trading_mode(session, fixture.owner, gold["id"], "full", by="owner_tap")
        lead = await wake(fixture, lonora)

        # cancel_run ends the team agent's current run, never Lonora's own (3.1.2).
        cancelled = await call(lead, "agent_control", agent_id=gold["id"], action="cancel_run")
        assert cancelled["changed"] is True and cancelled["cancelled_runs"] == 1
        assert cancelled["owner_line"] == "required"
        async with fixture.runtime.db.sessions() as session:
            assert (await session.get(RunRow, gold_run["id"])).status == "cancelled"  # type: ignore[union-attr]
            assert (await session.get(RunRow, lead.lease.run_id)).status != "cancelled"  # type: ignore[union-attr]
            assert (await session.get(RunRow, queued["id"])).status == "queued"  # type: ignore[union-attr]
        again = await call(lead, "agent_control", agent_id=gold["id"], action="cancel_run")
        assert again["changed"] is False and "owner_line" not in again

        # set_ask switches it to Ask with no card and no owner message (4.2.2).
        asked = await call(lead, "agent_control", agent_id=gold["id"], action="set_ask")
        assert asked["changed"] is True and asked["trading_mode"] == "ask"
        # The same switch as trading_mode_ask: it says what signed grants still decide.
        assert asked["active_signed_grants"] == 0 and asked["owner_line"] == "required"
        async with fixture.runtime.db.sessions() as session:
            assert await trading_mode(session, fixture.owner, gold["id"]) == "ask"
        async with fixture.runtime.db.sessions() as session, session.begin():
            await set_trading_mode(session, fixture.owner, gold["id"], "full", by="owner_tap")
        # Through trading_mode_ask, Lonora's switch of a team agent carries the line too.
        tool = await call(lead, "trading_mode_ask", agent_id=gold["id"])
        assert tool["changed"] is True and tool["owner_line"] == "required"
        assert "owner_line" not in await call(lead, "trading_mode_ask", agent_id=gold["id"])

        # Lonora's pause raises no card (only the five fixed cards, 10.3): one line instead.
        async def pause_cards() -> int:
            async with fixture.runtime.db.sessions() as session:
                return len(
                    list(
                        await session.scalars(
                            select(OwnerActionRow.id).where(
                                OwnerActionRow.owner_id == fixture.owner,
                                OwnerActionRow.kind == "supervision_paused",
                            )
                        )
                    )
                )

        cards = await pause_cards()
        paused = await call(lead, "agent_control", agent_id=gold["id"], action="pause")
        assert paused["changed"] is True and paused["owner_line"] == "required"
        assert await pause_cards() == cards

        # A team agent leads no one (3.2.2): Lonora's powers are refused to it.
        team = await wake(fixture, peer)
        assert (
            await refused(team, "agent_control", agent_id=gold["id"], action="resume")
            == "supervision_required"
        )
        for action in ("cancel_run", "set_ask"):
            assert (
                await refused(team, "agent_control", agent_id=gold["id"], action=action)
                == "agent_control_lead_only"
            )
        assert (
            await refused(lead, "agent_control", agent_id=lonora["id"], action="set_ask")
            == "supervision_self_target"
        )
    finally:
        await fixture.close()
