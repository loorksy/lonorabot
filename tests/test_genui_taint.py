"""The card-send taint (docs/genui.md #12, §8.5; PR #50 review M1-M6).

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
async def test_a_run_started_from_a_tainted_parent_inherits_the_taint_and_passes_it_on() -> None:
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
async def test_a_task_a_tainted_run_starts_is_tainted_with_its_run() -> None:
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


@pytest.mark.asyncio
async def test_a_subagent_spawned_by_a_tainted_run_is_tainted() -> None:
    """M1 through the real tool: ``subagent_spawn`` from a card's send starts a tainted
    Run that is not a submission, and its own work is tainted in turn."""
    from lonora_db.genui_taint import SUBMIT, TAINT
    from test_proactive_wakes import call

    fixture = await open_fixture()
    try:
        _, submit_run, context = await submit_lease(fixture)
        spawned = await call(context, "subagent_spawn", task="Check the gold quote.")
        child = await run_row(fixture, spawned["id"])
        origin = (await run_row(fixture, submit_run["id"])).model_metadata[SUBMIT]
        assert child.parent_run_id == submit_run["id"]
        assert child.model_metadata[TAINT] == origin and SUBMIT not in child.model_metadata
        assert await tainted(fixture, spawned["id"])
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_an_opportunity_saved_by_tainted_work_wakes_tainted() -> None:
    """Review round 4 (a): an opportunity a card's send saved keeps the taint, so its wake
    (a ``trigger='watch'`` Run with no parent) cannot spend the signed grant."""
    from lonora_contracts.domain import utcnow
    from test_proactive_wakes import retire, simulation

    fixture = await open_fixture()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        card, _, context = await submit_lease(fixture)
        saved = await tool(
            context,
            "market_opportunity_create",
            {
                "account_id": connection,
                "symbol": "XAUUSD",
                "timeframe": "1m",
                "setup_key": "card-breakout",
                "definition": {
                    "direction": "BUY",
                    "rationale": "From a card",
                    "entry_condition": "Above 2450",
                    "invalidation_condition": "Below 2400",
                    "strategy_version": "card-v1",
                    "expires_at": (utcnow() + timedelta(hours=1)).isoformat(),
                },
            },
        )
        assert await row_taint(fixture, "opportunity", saved["id"]) is not None
        assert await tainted(fixture, await wake(fixture, card, opportunity_id=saved["id"]))
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_the_continuation_of_a_card_a_tainted_run_proposed_is_tainted() -> None:
    """Review round 4 (b): a card a card's send proposed (e.g. a trust_source card) and
    the owner tapped continues in a Run that keeps the proposing Run's taint."""
    from lonora_contracts.domain import utcnow
    from lonora_db.owner_actions import continue_after_card
    from lonora_db.schema import OwnerActionRow, RunRow

    fixture = await open_fixture()
    try:
        card, submit_run, _ = await submit_lease(fixture)
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = OwnerActionRow(
                owner_id=fixture.owner,
                agent_id=card.agent["id"],
                thread_id=card.thread["id"],
                run_id=submit_run["id"],
                source="agent",
                kind="trust_source",
                subject="source:card-test",
                payload={"source_kind": "mcp", "identifier": "card-test"},
                payload_hash="0" * 64,
                status="confirmed",
                expires_at=utcnow() + timedelta(hours=1),
            )
            session.add(row)
            await session.flush()
            continued = await continue_after_card(session, row)
            assert continued is not None
            continued_id = continued.id
            stored = await session.get(RunRow, continued_id)
            assert stored is not None and stored.parent_run_id is None
        assert await tainted(fixture, continued_id)
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_tainted_peers_outcome_taints_the_run_it_returns_to() -> None:
    """outcome_return: a tainted child's outcome steers its untainted parent, which then
    carries the taint, as does a follow-up started from it."""
    from lonora_agent.collaboration.outcome_return import return_outcome
    from lonora_contracts.runs import RunRequest
    from lonora_db.genui_taint import TAINT
    from lonora_db.runs import create_run
    from lonora_db.schema import RunRow

    fixture = await open_fixture()
    try:
        card, submit_run, _ = await submit_lease(fixture)
        parent = await fixture.run(card.agent, card.thread)
        assert not await tainted(fixture, parent["id"])
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, parent["id"], with_for_update=True)
            assert run is not None
            run.status = "running"
            child = await create_run(
                session,
                fixture.owner,
                RunRequest(
                    thread_id=card.thread["id"],
                    agent_id=card.agent["id"],
                    trigger="peer",
                    parent_run_id=parent["id"],
                    metadata={TAINT: {"message_id": "from-a-card"}},
                ),
            )
            child.status, child.result = "completed", "peer result"
            child_id = child.id
        await return_outcome(fixture.runtime.db, child_id)
        assert (await run_row(fixture, parent["id"])).model_metadata.get(TAINT)
        assert await tainted(fixture, parent["id"])
        del submit_run
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_collaboration_synthesis_over_a_tainted_participant_is_tainted() -> None:
    from lonora_db.collaboration import participants_taint
    from lonora_db.genui_taint import TAINT
    from lonora_db.schema import RunRow

    fixture = await open_fixture()
    try:
        card, submit_run, _ = await submit_lease(fixture)
        clean = await fixture.run(card.agent, card.thread)
        async with fixture.runtime.db.sessions() as session:
            runs = [await session.get(RunRow, i) for i in (clean["id"], submit_run["id"])]
            assert all(r is not None for r in runs)
            assert TAINT in await participants_taint(session, runs)  # type: ignore[arg-type]
            assert await participants_taint(session, runs[:1]) == {}  # type: ignore[arg-type]
    finally:
        await fixture.close()


def _goal_body(connection: str, steps: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    return {
        "title": "Card goal",
        "objective": "Wait for gold",
        "account_id": connection,
        "symbol": "XAUUSD",
        "maximum_volume": "0.1",
        "max_trade_actions": 1,
        "steps": steps
        or [
            {"id": "look", "title": "Inspect", "kind": "analysis"},
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
            },
        ],
    }


@pytest.mark.asyncio
@pytest.mark.parametrize("change", ["create", "plan", "complete", "toggle"])
async def test_a_goal_tainted_work_creates_or_changes_wakes_tainted(change: str) -> None:
    """goal_create, goal_plan, goal_step_complete and goal_toggle from a tainted Run each
    taint the goal, so its later wakes (wake_goal: goal_id, no parent) are tainted."""
    from test_proactive_wakes import retire, simulation

    fixture = await open_fixture()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        card, _, context = await submit_lease(fixture)
        if change == "create":
            goal = await tool(context, "goal_create", _goal_body(connection))
        else:
            goal = await fixture.request(
                "POST",
                "/trading/goals",
                {
                    **_goal_body(connection),
                    "agent_id": card.agent["id"],
                    "thread_id": card.thread["id"],
                },
            )
            assert await row_taint(fixture, "goal", goal["id"]) is None
            if change == "plan":
                steps = _goal_body(connection)["steps"]
                await tool(
                    context,
                    "goal_plan",
                    {"goal_id": goal["id"], "version": goal["version"], "steps": steps},
                )
            elif change == "complete":
                await tool(
                    context,
                    "goal_step_complete",
                    {"goal_id": goal["id"], "step_id": "look", "note": "Seen"},
                )
            else:
                paused = await tool(
                    context,
                    "goal_control",
                    {"goal_id": goal["id"], "version": goal["version"], "action": "pause"},
                )
                # A paused goal never wakes; resumed, its wake shows the taint.
                await tool(
                    context,
                    "goal_control",
                    {"goal_id": goal["id"], "version": paused["version"], "action": "resume"},
                )
        assert await row_taint(fixture, "goal", goal["id"]) is not None
        assert await tainted(fixture, await wake(fixture, card, goal_id=goal["id"]))
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_task_control_from_tainted_work_taints_the_task_and_its_runs() -> None:
    """tools/tasks.py control: a tainted Run that revises or pauses an owner's Task taints
    it; the Task's own Run, resumed in place, follows."""
    from test_proactive_wakes import call

    fixture = await open_fixture()
    try:
        card, _, tainted_context = await submit_lease(fixture)
        own = await owner_context(fixture, card)
        task = await call(own, "task_start", title="Owner task", description="Mine")
        task_run = task["runs"][0]["id"]
        assert not await tainted(fixture, task_run)
        await tool(
            tainted_context,
            "task_control",
            {"task_id": task["id"], "action": "pause", "expected_version": task["version"]},
        )
        assert await row_taint(fixture, "ticket", task["id"]) is not None
        assert await tainted(fixture, task_run)
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_waiting_on_a_goal_target_from_tainted_work_taints_goal_and_routine() -> None:
    """goals.py wait_for_goal_target: the review routine it writes, and the goal, carry
    the taint of the Run that waited."""
    from lonora_trading.goals import wait_for_goal_target
    from test_proactive_wakes import retire, simulation

    fixture = await open_fixture()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        card, _, context = await submit_lease(fixture)
        goal = await fixture.request(
            "POST",
            "/trading/goals",
            {
                **_goal_body(connection),
                "agent_id": card.agent["id"],
                "thread_id": card.thread["id"],
            },
        )
        waited = await wait_for_goal_target(
            fixture.runtime.db, fixture.owner, goal["id"], "look", context.lease
        )
        routine = waited["wake_source"]["id"]
        assert await row_taint(fixture, "goal", goal["id"]) is not None
        assert await row_taint(fixture, "routine", routine) is not None
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_tainted_task_owned_watch_resumes_its_task_tainted() -> None:
    """watchers.py: a watch an owner's Task created, retargeted by tainted work, fires into
    the Task's own Run; the Task, and so that Run, carries the taint."""
    from lonora_market.watchers import check_watches
    from test_proactive_wakes import call, retire, simulation

    fixture = await open_fixture()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        card, _, tainted_context = await submit_lease(fixture)
        own = await owner_context(fixture, card)
        task = await call(own, "task_start", title="Watch gold", description="Owner task")
        task_run = task["runs"][0]
        task_context = await fixture.lease(
            {
                "id": task_run["id"],
                "agent_id": card.agent["id"],
                "thread_id": task["work_thread_id"],
            }
        )
        watch = await call(
            task_context,
            "watch_create",
            account_id=connection,
            symbol="XAUUSD",
            condition="above",
            level="300",
            prompt="Tell me.",
        )
        assert not await tainted(fixture, task_run["id"])
        await call(tainted_context, "watch_update", watch_id=watch["id"], level="50")
        fired = await check_watches(
            fixture.runtime.db, task_context.brokers, owner_id=fixture.owner
        )
        assert fired >= 1
        assert await row_taint(fixture, "ticket", task["id"]) is not None
        assert await tainted(fixture, task_run["id"])
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_supervisor_resuming_work_from_tainted_work_taints_it() -> None:
    """supervision.py control_work: a supervisor's resume of another agent's routine, from
    a card's send, taints that routine, so its later wakes are tainted."""
    from test_proactive_wakes import call
    from test_supervision import grant

    fixture = await open_fixture()
    try:
        card, _, lead_context = await submit_lease(fixture)
        gold = await fixture.agent("Gold")
        gold_thread = await fixture.conversation(gold)
        gold_context = await fixture.lease(await fixture.run(gold, gold_thread))
        routine = await call(
            gold_context, "routine_create", prompt="Check gold.", interval_seconds=3600
        )
        await grant(fixture, card.agent, gold)
        target = {"agent_id": gold["id"], "target": "routine", "target_id": routine["id"]}
        await call(lead_context, "agent_control", action="pause", **target)
        assert await row_taint(fixture, "routine", routine["id"]) is None
        resumed = await call(lead_context, "agent_control", action="resume", **target)
        assert resumed["changed"] is True
        assert await row_taint(fixture, "routine", routine["id"]) is not None
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_owner_words_skip_a_hidden_send_and_read_the_owners_earlier_message() -> None:
    """owner_words.py (#38): for a Run whose window reaches another Run's queued send, the
    send is skipped, not read: the owner's own earlier message is still their words."""
    from lonora_db.owner_words import owner_typed_message
    from lonora_db.schema import RunRow

    fixture = await open_fixture()
    try:
        card = await Card(fixture).open()
        typed = await fixture.request(
            "POST", f"/threads/{card.thread['id']}/messages", {"content": "راقب الذهب"}
        )
        owner_run = typed["run_ids"][0]
        response = await card.post(card.body({"price": 2490}))
        assert response.status_code == 202
        send = response.json()["message"]
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, owner_run, with_for_update=True)
            assert run is not None
            run.input_seq = send["seq"]  # its window now reaches the queued send
            words = await owner_typed_message(session, run)
            assert words is not None and words.id == typed["message"]["id"]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_conversation_recall_hides_unfinished_sends_and_labels_card_words() -> None:
    """conversation.py (#44): recall applies rules V/N and labels a finished send
    ``owner_via_card``."""
    from lonora_db.genui_submit import mark_submit_started
    from lonora_db.schema import RunRow
    from lonora_memory.conversation import ConversationRecallScope, conversation_candidates

    fixture = await open_fixture()
    try:
        card = await Card(fixture).open()
        ran = await card.post(card.body({"price": 2401}))
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, ran.json()["run_ids"][0], with_for_update=True)
            assert run is not None
            await mark_submit_started(session, run)
            run.status = "completed"
        await card.place()
        waiting = await card.post(card.body({"price": 2402}))
        assert waiting.status_code == 202
        top = waiting.json()["message"]["seq"] + 1
        scope = ConversationRecallScope(
            thread_id=card.thread["id"], input_seq=top + 1, before_seq=top, unloaded_through=top
        )
        async with fixture.runtime.db.sessions() as session:
            found, _, _ = await conversation_candidates(
                session, fixture.owner, card.agent["id"], scope, "تنبيهًا"
            )
        kinds = {item.provenance["message_id"]: item.provenance["author_kind"] for item in found}
        assert kinds.get(ran.json()["message"]["id"]) == "owner_via_card"
        assert waiting.json()["message"]["id"] not in kinds
    finally:
        await fixture.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("origin", ["owner", "ui_submit"])
async def test_another_runs_send_never_selects_this_runs_skills(origin: str) -> None:
    """skills.py (#44): the latest message selects a Run's skills only when it is the
    owner's own, or the Run's own send; another Run's card send never does (rule V)."""
    from lonora_agent.context.skills import read_skill_context
    from lonora_contracts.runs import RunRequest
    from lonora_db.runs import create_run, run_data
    from lonora_db.schema import AgentRow, MessageRow, ThreadRow
    from lonora_tools.loader import load_tools

    fixture = await open_fixture()
    try:
        card = await Card(fixture).start()
        async with fixture.runtime.db.sessions() as session, session.begin():
            thread = await session.get(ThreadRow, card.thread["id"], with_for_update=True)
            assert thread is not None
            session.add(
                MessageRow(
                    thread_id=thread.id,
                    role="user",
                    seq=thread.next_seq,
                    content="[skill:position-management]",
                    origin=origin,
                    ui_submit={"run_id": "another-run"} if origin == "ui_submit" else None,
                )
            )
            thread.next_seq += 1
            await session.flush()
            run = run_data(
                await create_run(
                    session,
                    fixture.owner,
                    RunRequest(thread_id=thread.id, agent_id=card.agent["id"], trigger="user"),
                )
            )
        context = await fixture.lease(run)
        async with fixture.runtime.db.sessions() as session:
            agent = await session.get(AgentRow, card.agent["id"])
            assert agent is not None
            selected = await read_skill_context(session, context, agent, load_tools())
        ids = {dict(section.attributes).get("id") for section in selected.sections}
        assert ("position-management" in ids) is (origin == "owner")
    finally:
        await fixture.close()
