"""Provenance of a generated card's send (mandate 6.10).

A card's send is input to the agent's own judgment. Its mark is the one Run the send
started (``ui_submit_origin``), and it never spreads to the agent's later watches,
routines, tickets, Tasks, goals, opportunities or wakes, nor to a peer, follow-up or
child Run. The same holds for a provisional voice handoff. Unfinished sends stay out of
search, recall and skill selection. Runs on the real migrated PostgreSQL schema (skipped
without ``LONORA_DATABASE_URL``).
"""

import json
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


async def marked(fixture: Any, run_id: str) -> bool:
    """Whether the Run counts as a card's send or a provisional handoff (6.10)."""
    from lonora_db.schema import RunRow
    from lonora_trading.account_authority import provisional_voice

    async with fixture.runtime.db.sessions() as session:
        row = await session.get(RunRow, run_id)
        assert row is not None
        return await provisional_voice(session, row)


async def started(fixture: Any, card: Card, parent: str | None = None, **metadata: Any) -> str:
    """A Run the way a watcher, routine, ticket, goal, peer or follow-up starts one."""
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
                parent_run_id=parent,
                metadata=metadata,
            ),
        )
        return row.id


@pytest.mark.asyncio
async def test_a_cards_send_marks_its_own_run_and_nothing_it_starts_or_wakes() -> None:
    """6.10: the mark never spreads to later watches, routines or wakes."""
    from test_proactive_wakes import call, retire, simulation

    fixture = await open_fixture()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        card, submit_run, context = await submit_lease(fixture)
        assert await marked(fixture, submit_run["id"])
        watch = await call(
            context,
            "watch_create",
            account_id=connection,
            symbol="XAUUSD",
            condition="above",
            level="2450",
            prompt="Tell the owner gold crossed 2450.",
        )
        # The watch it created wakes an ordinary Run of the agent.
        assert not await marked(fixture, await started(fixture, card, watch_id=watch["id"]))
        # So does a peer, follow-up or child Run of the send.
        assert not await marked(fixture, await started(fixture, card, parent=submit_run["id"]))
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_provisional_voice_handoff_marks_only_its_own_run() -> None:
    from lonora_db.schema import RunRow

    fixture = await open_fixture()
    try:
        card = await Card(fixture).open()
        handoff = await started(fixture, card)
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, handoff, with_for_update=True)
            assert row is not None
            row.model_metadata = {**row.model_metadata, "voice_handoff": {"finalized": False}}
        assert await marked(fixture, handoff)
        assert not await marked(fixture, await started(fixture, card, parent=handoff))
    finally:
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
