"""The card-send taint (GENUI_PLAN §0 #12, §8.5; PR #50 review M1-M6).

Every durable thing tainted work creates or changes stores the taint, every wake or start
from it is tainted, and the taint is never the submission marker the queue rules read.
Runs on the real migrated PostgreSQL schema (skipped without ``LONORA_DATABASE_URL``).
"""

import json
from datetime import timedelta
from typing import Any

import pytest
from test_genui_submit import Card, open_fixture


async def submit_lease(fixture: Any) -> tuple[Card, dict[str, Any], Any]:
    """A card's send and its own Run, leased as the worker would."""
    card = await Card(fixture).open()
    response = await card.post(card.body({"price": 2450}))
    assert response.status_code == 202, response.text
    run = {
        "id": response.json()["run_ids"][0],
        "agent_id": card.agent["id"],
        "thread_id": card.thread["id"],
    }
    return card, run, await fixture.lease(run)


async def run_row(fixture: Any, run_id: str) -> Any:
    from lonora_db.schema import RunRow

    async with fixture.runtime.db.sessions() as session:
        row = await session.get(RunRow, run_id)
        assert row is not None
        return row


async def tainted(fixture: Any, run_id: str) -> bool:
    from lonora_db.schema import RunRow
    from lonora_trading.account_authority import provisional_voice

    async with fixture.runtime.db.sessions() as session:
        row = await session.get(RunRow, run_id)
        assert row is not None
        return await provisional_voice(session, row)


async def row_taint(fixture: Any, kind: Any, identifier: str) -> Any:
    from lonora_db.genui_taint import row_taint as read

    async with fixture.runtime.db.sessions() as session:
        return await read(session, kind, identifier)


async def wake(fixture: Any, card: Card, **metadata: Any) -> Any:
    """A wake Run the way a watcher, routine, ticket or goal starts one."""
    from lonora_contracts.runs import RunRequest
    from lonora_db.runs import create_run

    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await create_run(
            session,
            fixture.owner,
            RunRequest(
                thread_id=card.thread["id"],
                agent_id=card.agent["id"],
                trigger="watch",
                metadata=metadata,
            ),
        )
        return row.id


async def tool(context: Any, name: str, arguments: dict[str, Any]) -> dict[str, Any]:
    from uuid import uuid4

    from lonora_adapter_kit.types import ToolCall
    from lonora_tools.loader import load_tools

    return await load_tools().execute(
        ToolCall(id=name + "-" + uuid4().hex, name=name, arguments=arguments), context
    )


async def owner_context(fixture: Any, card: Card) -> Any:
    """An untainted Run of the same agent (the owner's own turn), leased."""
    return await fixture.lease(await fixture.run(card.agent, card.thread))


@pytest.mark.asyncio
async def test_a_wake_from_a_tainted_watch_is_tainted_and_never_a_queued_submit() -> None:
    """The watch keeps the taint in the ledger, its wake Run inherits it in ``create_run``
    and is not a submission: rule L never expires it and it blocks no new send (M6)."""
    from lonora_db.genui_submit import expire_submits, queued_submit
    from lonora_db.genui_taint import SUBMIT, TAINT
    from lonora_db.schema import RunRow
    from test_proactive_wakes import call, retire, simulation

    fixture = await open_fixture()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        card, submit_run, context = await submit_lease(fixture)
        created = await call(
            context,
            "watch_create",
            account_id=connection,
            symbol="XAUUSD",
            condition="above",
            level="2450",
            prompt="Tell the owner gold crossed 2450.",
        )
        origin = (await run_row(fixture, submit_run["id"])).model_metadata[SUBMIT]
        assert await row_taint(fixture, "watch", created["id"]) == origin
        woken = await wake(fixture, card, watch_id=created["id"])
        row = await run_row(fixture, woken)
        assert row.model_metadata[TAINT] == origin and SUBMIT not in row.model_metadata
        assert await tainted(fixture, woken)
        async with fixture.runtime.db.sessions() as session, session.begin():
            stored = await session.get(RunRow, woken, with_for_update=True)
            assert stored is not None
            stored.created_at = stored.created_at - timedelta(minutes=45)
        async with fixture.runtime.db.sessions() as session, session.begin():
            expired = await expire_submits(session, card.thread["id"])
            assert woken not in [run.id for run in expired]
            assert await queued_submit(session, card.thread["id"], card.agent["id"]) is None
        assert (await run_row(fixture, woken)).status == "queued"
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_peer_and_subagent_runs_inherit_the_taint_and_pass_it_to_their_work() -> None:
    """M1: a Run started from a tainted one (peer, collaboration, subagent: all through
    ``parent_run_id``) stores the taint, and the watch and routine it creates wake tainted."""
    from lonora_contracts.runs import RunRequest
    from lonora_db.genui_taint import SUBMIT, TAINT
    from lonora_db.runs import create_run, run_data
    from test_proactive_wakes import call, retire, simulation

    fixture = await open_fixture()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        card, submit_run, _ = await submit_lease(fixture)
        async with fixture.runtime.db.sessions() as session, session.begin():
            child = run_data(
                await create_run(
                    session,
                    fixture.owner,
                    RunRequest(
                        thread_id=card.thread["id"],
                        agent_id=card.agent["id"],
                        trigger="peer",
                        parent_run_id=submit_run["id"],
                        # A caller can never mark a Run as a submission.
                        metadata={SUBMIT: {"message_id": "forged"}},
                    ),
                )
            )
        stored = await run_row(fixture, child["id"])
        assert stored.model_metadata[TAINT]["message_id"] != "forged"
        assert SUBMIT not in stored.model_metadata
        context = await fixture.lease(child)
        watch = await call(
            context,
            "watch_create",
            account_id=connection,
            symbol="XAUUSD",
            condition="above",
            level="2500",
            prompt="Tell the owner.",
        )
        routine = await call(context, "routine_create", prompt="Check gold.", interval_seconds=3600)
        assert await row_taint(fixture, "watch", watch["id"]) is not None
        assert await row_taint(fixture, "routine", routine["id"]) is not None
        assert await tainted(fixture, await wake(fixture, card, watch_id=watch["id"]))
        assert await tainted(fixture, await wake(fixture, card, routine_id=routine["id"]))
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_ticket_tainted_work_wrote_starts_tainted_whoever_starts_it() -> None:
    """M3: ``ticket_create`` in a tainted Run taints the ticket; a later start from an
    untainted Run (or the owner) is tainted all the same."""
    from lonora_agent.automation.background import start_ticket
    from test_proactive_wakes import call

    fixture = await open_fixture()
    try:
        _, _, context = await submit_lease(fixture)
        board = await tool(context, "board_create", {"title": "Card work"})
        ticket = await call(
            context,
            "ticket_create",
            board_id=board["id"],
            title="Follow the gold alert",
        )
        assert await row_taint(fixture, "ticket", ticket["id"]) is not None
        started = await start_ticket(fixture.runtime.db, fixture.owner, ticket["id"])
        assert await tainted(fixture, started["id"])
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_task_a_tainted_run_starts_is_tainted_with_every_run_it_resumes() -> None:
    from lonora_db.genui_taint import TAINT
    from test_proactive_wakes import call

    fixture = await open_fixture()
    try:
        _, _, context = await submit_lease(fixture)
        task = await call(context, "task_start", title="Card task", description="From a card")
        assert await row_taint(fixture, "ticket", task["id"]) is not None
        run_id = task["runs"][0]["id"]
        assert (await run_row(fixture, run_id)).model_metadata.get(TAINT)
        assert await tainted(fixture, run_id)
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_tainted_work_that_changes_untainted_watches_and_routines_taints_them() -> None:
    """M4: ``watch_update``, ``watch_resume`` and ``routine_toggle`` from a tainted Run
    taint the row, so its later wakes cannot spend the grant on card words."""
    from test_proactive_wakes import call, retire, simulation

    fixture = await open_fixture()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        card, _, tainted_context = await submit_lease(fixture)
        own = await owner_context(fixture, card)
        watches = [
            await call(
                own,
                "watch_create",
                account_id=connection,
                symbol="XAUUSD",
                condition="above",
                level=str(2600 + index),
                prompt="Tell the owner.",
            )
            for index in range(2)
        ]
        routine = await call(own, "routine_create", prompt="Check gold.", interval_seconds=3600)
        for item in watches:
            assert await row_taint(fixture, "watch", item["id"]) is None
        assert await row_taint(fixture, "routine", routine["id"]) is None
        assert not await tainted(fixture, await wake(fixture, card, watch_id=watches[0]["id"]))

        await call(tainted_context, "watch_update", watch_id=watches[0]["id"], level="2700")
        await call(own, "watch_pause", watch_id=watches[1]["id"])
        await call(tainted_context, "watch_resume", watch_id=watches[1]["id"])
        await call(tainted_context, "routine_toggle", routine_id=routine["id"], enabled=True)
        for item in watches:
            assert await row_taint(fixture, "watch", item["id"]) is not None
            assert await tainted(fixture, await wake(fixture, card, watch_id=item["id"]))
        assert await tainted(fixture, await wake(fixture, card, routine_id=routine["id"]))
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_goal_wait_in_a_tainted_run_taints_the_goal_and_its_wake_source() -> None:
    """M2: ``goal_wait`` writes its watch through the repository; the watch and the goal
    carry the taint, and the goal's wake and its watch's wake are tainted."""
    from test_proactive_wakes import call, retire, simulation

    fixture = await open_fixture()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        card, _, context = await submit_lease(fixture)
        goal = await fixture.request(
            "POST",
            "/trading/goals",
            {
                "agent_id": card.agent["id"],
                "thread_id": card.thread["id"],
                "title": "Card goal",
                "objective": "Wait for gold",
                "account_id": connection,
                "symbol": "XAUUSD",
                "maximum_volume": "0.1",
                "max_trade_actions": 1,
                "steps": [
                    {
                        "id": "wait",
                        "title": "Wait for gold",
                        "kind": "watch",
                        "condition": {
                            "kind": "price",
                            "account_id": connection,
                            "symbol": "XAUUSD",
                            "condition": "above",
                            "level": "200",
                            "prompt": "Recheck gold",
                        },
                    }
                ],
            },
        )
        assert await row_taint(fixture, "goal", goal["id"]) is None
        waiting = await call(context, "goal_wait", goal_id=goal["id"], step_id="wait")
        source = waiting["wake_source"]["id"]
        assert await row_taint(fixture, "goal", goal["id"]) is not None
        assert await row_taint(fixture, "watch", source) is not None
        assert await tainted(fixture, await wake(fixture, card, goal_id=goal["id"]))
        assert await tainted(fixture, await wake(fixture, card, watch_id=source))
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_search_internal_hides_unfinished_submissions_and_labels_card_words() -> None:
    """M5: rules V and N hold in ``search_internal`` too, and a visible card send is
    labelled ``owner_via_card``, never the owner's own words."""
    from lonora_db.genui_submit import mark_submit_started
    from lonora_db.schema import RunRow
    from lonora_tools.search import agent_search

    fixture = await open_fixture()
    try:
        card, submit_run, _ = await submit_lease(fixture)
        found = await agent_search(fixture.runtime.db, fixture.owner, card.agent["id"], "تنبيه")
        assert not [
            m
            for m in found["messages"]
            if m["thread_id"] == card.thread["id"] and m["role"] != "assistant"
        ]
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, submit_run["id"], with_for_update=True)
            assert run is not None
            # It ran (rule N records the start) and ended (rule V): now it is history.
            await mark_submit_started(session, run)
            run.status = "completed"
        found = await agent_search(fixture.runtime.db, fixture.owner, card.agent["id"], "تنبيه")
        mine = [m for m in found["messages"] if m["thread_id"] == card.thread["id"]]
        sent = [m for m in mine if m["content"].startswith("أنشئ تنبيهًا")]
        assert sent and all(m["role"] == "owner_via_card" for m in sent)
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_rules_v_and_n_hold_in_session_search_and_compaction() -> None:
    """A send that ran and ended is history, labelled ``owner_via_card``; one that never
    ran is only the note; one still waiting is outside every other Run's view."""
    from unittest.mock import patch

    from lonora_adapter_kit.types import ModelReply
    from lonora_agent.context.compaction import compact_history
    from lonora_contracts.model_routing import ModelSelection
    from lonora_db.genui_submit import mark_submit_started
    from lonora_db.schema import MessageRow, RunRow, ThreadRow
    from lonora_memory.sessions import discover, history_scope, read

    fixture = await open_fixture()
    try:
        card = await Card(fixture).open()
        thread_id = card.thread["id"]

        async def send(price: int) -> dict[str, Any]:
            await card.place()  # a fresh card each time: a sent card stays locked
            response = await card.post(card.body({"price": price}))
            assert response.status_code == 202, response.text
            return response.json()

        ran = await send(2401)
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, ran["run_ids"][0], with_for_update=True)
            assert run is not None
            await mark_submit_started(session, run)
            run.status = "completed"
        never = await send(2402)
        await fixture.request(
            "POST", f"/threads/{thread_id}/messages/{card.message_id}/ui-state/1/unlock"
        )
        waiting = await send(2403)
        # Enough later conversation for compaction to summarize the older part.
        async with fixture.runtime.db.sessions() as session, session.begin():
            thread = await session.get(ThreadRow, thread_id, with_for_update=True)
            assert thread is not None
            for index in range(130):
                session.add(
                    MessageRow(
                        thread_id=thread_id,
                        agent_id=None if index % 2 == 0 else card.agent["id"],
                        role="user" if index % 2 == 0 else "assistant",
                        seq=thread.next_seq,
                        content=f"رسالة لاحقة {index}",
                    )
                )
                thread.next_seq += 1

        # session_search: discover and read.
        async with fixture.runtime.db.sessions() as session:
            scope = await history_scope(session, fixture.owner, card.agent["id"])
            found = await discover(session, scope, "أنشئ تنبيهًا", thread_id=thread_id)
            page = await read(session, scope, thread_id, 0, limit=50)
        shown = {m["message_id"]: m for m in page["messages"]}
        assert shown[ran["message"]["id"]]["author"] == "owner_via_card"
        assert never["message"]["id"] not in shown and waiting["message"]["id"] not in shown
        matches = json.dumps(found, ensure_ascii=False)
        assert never["message"]["id"] not in matches and waiting["message"]["id"] not in matches

        # Compaction: the shared summary input.
        other = await fixture.run(card.agent, card.thread)
        context = await fixture.lease(other)
        captured: list[str] = []

        async def complete(*args: Any, **kwargs: Any) -> Any:
            captured.append(args[1][-1].content)
            return ModelReply(text="ملخص"), ModelSelection(provider="openai", model="scripted")

        with patch.object(context.router, "complete", complete):
            await compact_history(context)
        assert captured
        summary_input = captured[0]
        assert "role='owner_via_card'" in summary_input and "2,401" in summary_input
        assert "طلب من بطاقة لم يُنفَّذ" in summary_input and "2,402" not in summary_input
        assert "2,403" not in "".join(captured)

    finally:
        await fixture.close()
