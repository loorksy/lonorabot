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
    from lonora_db.supervision import grant_supervision, revoke_supervision

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

        # A default grant as migration 0041 stored one changes nothing, so no profile lists
        # it (its Stop would change nothing); revoked, the lead role remains.
        async with fixture.runtime.db.sessions() as session, session.begin():
            default, _ = await grant_supervision(
                session, fixture.owner, lonora["id"], gold["id"], via="default"
            )
            default_id = default.id
        for agent_id in (gold["id"], lonora["id"]):
            view = await fixture.request("GET", f"/supervision?agent_id={agent_id}")
            assert view["supervises"] == [] and view["supervised_by"] == [], view
        async with fixture.runtime.db.sessions() as session, session.begin():
            await revoke_supervision(session, fixture.owner, default_id, via="owner_ui")

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
async def test_lonora_takes_no_grant_and_no_card_says_its_supervision_changed():
    """0.4: a grant to Lonora, or a revoke of one, would change nothing, so neither is made
    and no card says supervision was set or stopped."""
    database()
    from check_streaming import Fixture
    from lonora_db.owner_actions import (
        propose_supervision,
        raise_supervision_card,
        raise_supervision_stopped_card,
        stale_reason,
    )
    from lonora_db.personal_agent import ensure_personal_agent
    from lonora_db.schema import SupervisionGrantRow
    from lonora_db.supervision import grant_supervision, revoke_supervision
    from test_supervision import owner_says

    fixture = await Fixture().open()
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await ensure_personal_agent(session, fixture.owner)
            lonora = {"id": row.id, "name": row.name}
        gold, silver = await fixture.agent("Gold"), await fixture.agent("Silver")
        # Silver holds a default grant as migration 0041 stored one; Gold, made later, none.
        async with fixture.runtime.db.sessions() as session, session.begin():
            stored, _ = await grant_supervision(
                session, fixture.owner, lonora["id"], silver["id"], via="default"
            )
            stored_id = stored.id
        thread = await fixture.conversation(lonora)

        async def cards() -> list[dict[str, Any]]:
            response = await fixture.client.get(
                "/api/owner-actions", params={"thread_id": thread["id"]}
            )
            assert response.is_success, response.text
            return [
                item
                for item in response.json()
                if item["kind"].startswith("supervis") and item["id"] not in earlier
            ]

        # The database is shared: cards other tests left in Lonora's conversation (a
        # supervisor pausing Lonora's routine, a supervision set from its chat) are not this
        # test's.
        earlier: set[str] = set()
        earlier = {item["id"] for item in await cards()}
        # The owner asks Lonora to stop (or start) supervising: refused with the reason,
        # nothing revoked, and no Stopped card with Restore, nor an Undo card.
        told = await owner_says(fixture, lonora, thread, "توقفي عن الإشراف على الذهب والفضة")
        for action in ("revoke", "grant"):
            assert (
                await refused(
                    told,
                    "supervision_change",
                    action=action,
                    supervised_ids=[gold["id"], silver["id"]],
                )
                == "supervision_lead_needs_no_grant"
            )
        async with fixture.runtime.db.sessions() as session:
            kept = await session.get(SupervisionGrantRow, stored_id)
            assert kept is not None and kept.revoked_at is None
        assert await cards() == []
        # Nor does another agent name Lonora as the supervisor.
        silver_run = await owner_says(
            fixture, silver, await fixture.conversation(silver), "Let Lonora supervise Gold"
        )
        assert (
            await refused(
                silver_run,
                "supervision_change",
                action="grant",
                supervisor_id=lonora["id"],
                supervised_ids=[gold["id"]],
            )
            == "supervision_lead_needs_no_grant"
        )

        # A card naming Lonora as the supervisor is never live: Lonora already reaches both.
        payload = {"supervisor_id": lonora["id"], "supervised_ids": [gold["id"]]}
        async with fixture.runtime.db.sessions() as session, session.begin():
            assert (
                await stale_reason(session, fixture.owner, "supervise", payload)
                == "supervision_already_set"
            )
            with pytest.raises(LonoraError) as error:
                await propose_supervision(
                    session,
                    fixture.owner,
                    lonora["id"],
                    [gold["id"]],
                    card_id=str(uuid4()),
                    agent_id=lonora["id"],
                    thread_id=thread["id"],
                    run_id=None,
                )
            assert error.value.code == "owner_action_not_needed_supervision_already_set"
        # A Stopped card raised before this change offers no Restore: Lonora still reads.
        async with fixture.runtime.db.sessions() as session, session.begin():
            await revoke_supervision(session, fixture.owner, stored_id, via="owner_message")
            stopped = await raise_supervision_stopped_card(
                session,
                fixture.owner,
                [stored_id],
                card_key=str(uuid4()),
                agent_id=lonora["id"],
                thread_id=thread["id"],
                run_id=None,
            )
            assert stopped is not None
            stopped_id = stopped.id
        (listed,) = await cards()
        assert listed["id"] == stopped_id and listed["facts"]["supervision"]["active"] is False
        response = await fixture.client.post(
            f"/api/owner-actions/{stopped_id}/decision", json={"decision": "confirm"}
        )
        assert response.is_success, response.text
        settled = response.json()
        assert (settled["status"], settled["status_reason"]) == (
            "expired",
            "supervision_already_set",
        )
        # Nor does an Undo card raised before this change for a grant of Lonora's: Undo
        # would stop nothing, so it offers none and a tap revokes nothing.
        async with fixture.runtime.db.sessions() as session, session.begin():
            granted, _ = await grant_supervision(
                session, fixture.owner, lonora["id"], gold["id"], via="owner_message"
            )
            granted_id = granted.id
            undo = await raise_supervision_card(
                session,
                fixture.owner,
                [granted_id],
                card_key=str(uuid4()),
                agent_id=lonora["id"],
                thread_id=thread["id"],
                run_id=None,
            )
            assert undo is not None
            undo_id = undo.id
            assert (
                await stale_reason(session, fixture.owner, "supervision_created", undo.payload)
                == "supervision_already_set"
            )
        listed = next(item for item in await cards() if item["id"] == undo_id)
        assert listed["status"] == "pending"
        assert listed["facts"]["supervision"] == {
            "supervisor_name": lonora["name"],
            "supervised_names": [],
            "active": False,
            "lead": True,
        }
        response = await fixture.client.post(
            f"/api/owner-actions/{undo_id}/decision", json={"decision": "confirm"}
        )
        assert response.is_success, response.text
        settled = response.json()
        assert (settled["status"], settled["status_reason"]) == (
            "expired",
            "supervision_already_set",
        )
        async with fixture.runtime.db.sessions() as session:
            kept = await session.get(SupervisionGrantRow, granted_id)
            assert kept is not None and kept.revoked_at is None
    finally:
        await fixture.close()
