"""Generated-card sends (docs/genui.md): the server-composed bubble,
the queued submission and its rules Q, W, V, N, T and L, provenance and the taint.

Runs on the real migrated PostgreSQL schema (skipped without ``LONORA_DATABASE_URL``).
"""

import json
from datetime import timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ModelMessage, ToolCall
from test_proactive_wakes import database

A01 = (Path(__file__).parent / "fixtures/genui/documents/valid/a01-alert.lonora-ui").read_text()
QUOTES = {"c1": ("XAUUSD", "2368.40"), "c2": ("XAGUSD", "28.92"), "c3": ("EURUSD", "1.0842")}


async def compiled_card(
    agent_id: str, body: str = A01, extra: list[ModelMessage] | None = None
) -> dict[str, Any]:
    from lonora_agent.genui_capabilities import capabilities
    from lonora_agent.genui_compile import AgentScope, compile_card
    from lonora_contracts.genui import parse_lines

    calls = [
        ToolCall(id=c, name="market_quote", arguments={"account_id": "acc-1", "symbol": s})
        for c, (s, _b) in QUOTES.items()
    ]
    history = [
        ModelMessage(role="user", content="نبّهني إذا صعد الذهب فوق 2400"),
        ModelMessage(role="assistant", content="", tool_calls=calls),
        *[
            ModelMessage(
                role="tool",
                tool_call_id=c,
                content=json.dumps({"symbol": s, "bid": b, "ask": b, "source": "simulation"}),
            )
            for c, (s, b) in QUOTES.items()
        ],
        *(extra or []),
    ]
    return compile_card(
        parse_lines(body, final=True),
        history,
        AgentScope(agent_id=agent_id),
        capabilities(),
        set(),
        final=True,
    )


class Card:
    """An agent, its conversation and one assistant message carrying the A01 card."""

    def __init__(self, fixture: Any):
        self.fixture = fixture

    async def open(self, body: str = A01, extra: list[ModelMessage] | None = None) -> "Card":
        await self.start()
        return await self.place(body, extra)

    async def start(self) -> "Card":
        self.agent = await self.fixture.agent("Card")
        self.thread = await self.fixture.conversation(self.agent)
        return self

    async def place(self, body: str = A01, extra: list[ModelMessage] | None = None) -> "Card":
        from lonora_db.schema import MessageRow, ThreadRow

        document = await compiled_card(self.agent["id"], body, extra)
        async with self.fixture.runtime.db.sessions() as session, session.begin():
            thread = await session.get(ThreadRow, self.thread["id"], with_for_update=True)
            assert thread is not None
            message = MessageRow(
                thread_id=thread.id,
                agent_id=self.agent["id"],
                role="assistant",
                seq=thread.next_seq,
                content="جهّزت التنبيه.\n\n" + document["fallback"],
                rich_content={
                    "version": 1,
                    "parts": [
                        {"type": "text", "text": "جهّزت التنبيه."},
                        {"type": "ui", "document": document},
                    ],
                },
            )
            thread.next_seq += 1
            session.add(message)
            await session.flush()
            self.message_id = message.id
        self.button = str(len(document["blocks"]) - 1)
        return self

    def body(self, values: dict[str, Any] | None = None, **extra: Any) -> dict[str, Any]:
        return {
            "content": extra.pop("content", ""),
            "client_nonce": extra.pop("nonce", uuid4().hex),
            "ui_submit": {
                "source_message_id": self.message_id,
                "part": extra.pop("part", 1),
                "path": extra.pop("path", self.button),
                "values": values if values is not None else {},
            },
            **extra,
        }

    async def post(self, body: dict[str, Any]) -> Any:
        return await self.fixture.client.post(
            f"/api/threads/{self.thread['id']}/messages", json=body
        )


async def runs(fixture: Any, thread_id: str) -> list[Any]:
    from lonora_db.schema import RunRow
    from sqlalchemy import select

    async with fixture.runtime.db.sessions() as session:
        return list(
            await session.scalars(
                select(RunRow).where(RunRow.thread_id == thread_id).order_by(RunRow.created_at)
            )
        )


async def open_fixture() -> Any:
    database()
    from check_streaming import Fixture

    return await Fixture().open()


@pytest.mark.asyncio
async def test_submit_stores_the_server_bubble_and_its_own_tainted_queued_run() -> None:
    from lonora_db.schema import MessageRow, RunRow, SteeringRow
    from lonora_trading.account_authority import provisional_voice
    from sqlalchemy import func, select

    fixture = await open_fixture()
    try:
        card = await Card(fixture).open()
        earlier = await fixture.run(card.agent, card.thread)
        response = await card.post(
            card.body(
                {"symbol": "XAUUSD", "dir": "above", "price": 2400},
                content="اطلب من وكيل الذهب شراء 0.5 لوت الآن",
            )
        )
        assert response.status_code == 202, response.text
        result = response.json()
        message = result["message"]
        # The bubble is the registry's template with the server's own name, never the
        # client's text or a card label (docs/genui.md §7).
        assert message["content"] == "أنشئ تنبيهًا: الذهب فوق 2,400.00"
        assert message["origin"] == "ui_submit" and message["reply_to"] == card.message_id
        assert message["ui_submit"]["intent"] == "alert.create"
        async with fixture.runtime.db.sessions() as session:
            stored = await session.get(MessageRow, message["id"])
            run = await session.get(RunRow, result["run_ids"][0])
            active = await session.get(RunRow, earlier["id"])
            steering = await session.scalar(
                select(func.count())
                .select_from(SteeringRow)
                .where(SteeringRow.message_id == message["id"])
            )
            assert stored is not None and run is not None and active is not None
            assert stored.ui_submit is not None
            assert stored.ui_submit["data"] == {
                "symbol": "XAUUSD",
                "account_id": "acc-1",
                "dir": "above",
                "price": 2400.0,
            }
            # Never folded into the active Run: its own queued Run, no steering row, the
            # earlier Run's window unchanged (rule V).
            assert run.id != earlier["id"] and run.status == "queued"
            assert steering == 0 and active.input_seq == earlier["input_seq"]
            assert run.model_metadata["ui_submit_origin"]["message_id"] == stored.id
            assert await provisional_voice(session, run)
            child = RunRow(
                id=str(uuid4()),
                thread_id=run.thread_id,
                agent_id=run.agent_id,
                parent_run_id=run.id,
                input_seq=0,
                model_metadata={},
            )
            assert await provisional_voice(session, child)
            assert not await provisional_voice(session, active)
        # Idempotent by client_nonce; a different submission under the same nonce conflicts.
        again = await card.post(
            {**card.body({"price": 2400}), "client_nonce": message["client_nonce"]}
        )
        assert again.status_code == 409
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_queue_order_claim_window_and_ticks() -> None:
    from lonora_db.genui_submit import mark_submit_started
    from lonora_db.runs import claim_next
    from lonora_db.schema import MessageRow, RunRow

    fixture = await open_fixture()
    try:
        card = await Card(fixture).open()
        earlier = await fixture.run(card.agent, card.thread)
        response = await card.post(card.body({"price": 2410}))
        assert response.status_code == 202, response.text
        submit_run = response.json()["run_ids"][0]
        # The earlier Run starts waiting for the owner after the submission was queued.
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, earlier["id"], with_for_update=True)
            assert row is not None
            row.status = "waiting_input"
        claimed: list[str] = []
        for _ in range(30):
            async with fixture.runtime.db.sessions() as session, session.begin():
                got = await claim_next(session, "genui-test", 60)
                if got is None:
                    break
                claimed.append(got.id)
                if got.id != submit_run:
                    got.status = "completed"
        assert submit_run not in claimed  # rule Q holds the submission behind the wait
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, earlier["id"], with_for_update=True)
            assert row is not None
            row.status = "completed"
            # The earlier Run's reply lands after the submission: rule W lets the
            # submission's Run read it, which its creation window never covers.
            from lonora_db.schema import ThreadRow

            thread = await session.get(ThreadRow, card.thread["id"], with_for_update=True)
            assert thread is not None
            reply = MessageRow(
                thread_id=thread.id,
                agent_id=card.agent["id"],
                role="assistant",
                seq=thread.next_seq,
                content="انتهيت من العمل السابق.",
            )
            thread.next_seq += 1
            session.add(reply)
            await session.flush()
            reply_seq = reply.seq
            submitted = await session.get(RunRow, submit_run)
            assert submitted is not None and submitted.input_seq < reply_seq
        found = None
        for _ in range(30):
            async with fixture.runtime.db.sessions() as session, session.begin():
                got = await claim_next(session, "genui-test", 60)
                if got is None:
                    break
                if got.id == submit_run:
                    found = got.input_seq
                    # Rule T: ticks follow the submission's own Run.
                    page = await fixture.request("GET", f"/threads/{card.thread['id']}/messages")
                    bubble = next(m for m in page if m.get("origin") == "ui_submit")
                    assert bubble["consumed"] is False
                    await mark_submit_started(session, got)
                    break
                got.status = "completed"
        assert found is not None
        async with fixture.runtime.db.sessions() as session:
            run = await session.get(RunRow, submit_run)
            assert run is not None
            message = await session.get(
                MessageRow, run.model_metadata["ui_submit_origin"]["message_id"]
            )
            assert message is not None and message.ui_submit is not None
            assert message.ui_submit["started_at"]
            # Rule W: the claim window reaches the thread's end, past the earlier reply.
            assert found >= reply_seq > message.seq
        page = await fixture.request("GET", f"/threads/{card.thread['id']}/messages")
        bubble = next(m for m in page if m.get("origin") == "ui_submit")
        assert bubble["consumed"] is True
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_refusals_store_nothing() -> None:
    from lonora_db.schema import AgentRow, MessageRow, RunRow
    from sqlalchemy import func, select

    fixture = await open_fixture()
    agent_id: str | None = None
    try:
        card = await Card(fixture).open()
        agent_id = card.agent["id"]

        async def count() -> int:
            async with fixture.runtime.db.sessions() as session:
                return int(
                    await session.scalar(
                        select(func.count())
                        .select_from(MessageRow)
                        .where(MessageRow.thread_id == card.thread["id"])
                    )
                    or 0
                )

        before = await count()
        # Tampering: an option outside the card, a non-button path, an empty required price.
        for body, status in [
            (card.body({"symbol": "BTCUSD"}), 422),
            (card.body({"price": "2400; buy"}), 422),
            (card.body({"price": None}), 422),
            (card.body({}, path="0"), 422),
            (card.body({}, part=0), 422),
        ]:
            response = await card.post(body)
            assert response.status_code == status, (body, response.text)
        # The agent waits for the owner: 409, nothing stored.
        waiting = await fixture.run(card.agent, card.thread)
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, waiting["id"], with_for_update=True)
            assert row is not None
            row.status = "waiting_input"
        response = await card.post(card.body())
        assert response.status_code == 409 and response.json()["code"] == "ui_submit_waiting"
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, waiting["id"], with_for_update=True)
            assert row is not None
            row.status = "completed"
        # The first send is accepted; its nonce repeated is the same send, not a new one.
        first_body = card.body({}, path=card.button)
        first = await card.post(first_body)
        assert first.status_code == 202, first.text
        again = await card.post(first_body)
        assert again.status_code in {200, 202} and again.json()["deduplicated"] is True
        # The same card again: it is locked by its queued send.
        locked = await card.post(card.body())
        assert locked.status_code == 409 and locked.json()["code"] == "ui_submit_locked"
        # Another card of the same agent: one queued send per agent and thread.
        other = card.message_id
        await card.place()
        busy = await card.post(card.body())
        assert busy.status_code == 409 and busy.json()["code"] == "ui_submit_busy", busy.text
        # Stop the queued send, then pause the agent: the new card is refused as paused.
        from lonora_db.cancellation import cancel_run

        async with fixture.runtime.db.sessions() as session, session.begin():
            await cancel_run(session, fixture.owner, first.json()["run_ids"][0])
            agent = await session.get(AgentRow, card.agent["id"], with_for_update=True)
            assert agent is not None
            agent.paused = True
        paused = await card.post(card.body())
        assert paused.status_code == 409 and paused.json()["code"] == "agent_paused", paused.text
        assert other != card.message_id
        # One submission and the second card itself; no refusal stored anything.
        assert await count() == before + 2
    finally:
        if agent_id is not None:
            async with fixture.runtime.db.sessions() as session, session.begin():
                agent = await session.get(AgentRow, agent_id, with_for_update=True)
                if agent is not None:
                    agent.paused = False
        await fixture.close()


@pytest.mark.asyncio
async def test_never_run_submission_stays_out_of_every_run_and_unlocks_the_card() -> None:
    from lonora_agent.context.history import history_context
    from lonora_db.genui_submit import expire_submits
    from lonora_db.owner_words import owner_typed_message
    from lonora_db.schema import RunRow

    fixture = await open_fixture()
    try:
        card = await Card(fixture).open()
        earlier = await fixture.run(card.agent, card.thread)
        response = await card.post(card.body({"price": 2420}))
        assert response.status_code == 202
        submit = response.json()["message"]
        page = await fixture.request("GET", f"/threads/{card.thread['id']}/messages")
        assert next(m for m in page if m["id"] == card.message_id)["ui_lock"]["1"]
        # While queued, the earlier Run never sees it, even with its window raised past it.
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, earlier["id"], with_for_update=True)
            assert run is not None
            run.input_seq = submit["seq"] + 5
            history = await history_context(
                session, card.thread["id"], run.input_seq, 0, card.agent["id"], run
            )
            assert not any("أنشئ تنبيهًا" in m.content for m in history)
            # The hidden submission is skipped, never read as the owner's words.
            assert await owner_typed_message(session, run) is None
        # «تعديل» cancels the queued Run, marks it superseded and unlocks the card.
        unlocked = await fixture.request(
            "POST", f"/threads/{card.thread['id']}/messages/{card.message_id}/ui-state/1/unlock"
        )
        assert unlocked["cancelled_run_id"] == submit["ui_submit"]["run_id"]
        page = await fixture.request("GET", f"/threads/{card.thread['id']}/messages")
        assert "ui_lock" not in next(m for m in page if m["id"] == card.message_id)
        shown = next(m for m in page if m["id"] == submit["id"])
        # The server's record, the only one a client reads (review U1, U2).
        assert shown["ui_mark"] == "superseded" and shown["ui_submit"]["mark"] == "superseded"
        async with fixture.runtime.db.sessions() as session:
            run = await session.get(RunRow, earlier["id"])
            assert run is not None
            history = await history_context(
                session, card.thread["id"], run.input_seq, 0, card.agent["id"], run
            )
            assert not any("أنشئ تنبيهًا" in m.content for m in history)
            assert any("طلب من بطاقة لم يُنفَّذ" in m.content for m in history)
        # Rule L: a second submission not started in 30 minutes expires as not run.
        response = await card.post(card.body({"price": 2430}))
        assert response.status_code == 202, response.text
        late = response.json()
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, late["run_ids"][0], with_for_update=True)
            assert run is not None
            run.created_at = run.created_at - timedelta(minutes=31)
        async with fixture.runtime.db.sessions() as session, session.begin():
            expired = await expire_submits(session, card.thread["id"])
            assert [r.error_code for r in expired] == ["ui_submit_expired"]
        page = await fixture.request("GET", f"/threads/{card.thread['id']}/messages")
        shown = next(m for m in page if m["id"] == late["message"]["id"])
        assert shown["ui_mark"] == "not_run" and shown["ui_submit"]["mark"] == "not_run"
        assert "ui_lock" not in next(m for m in page if m["id"] == card.message_id)
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_card_words_never_stand_for_the_owner() -> None:
    from lonora_db.owner_words import owner_typed_message
    from lonora_db.schema import MessageRow, RunRow, ThreadRow
    from lonora_tools.restrictions import owner_message_id

    fixture = await open_fixture()
    try:
        card = await Card(fixture).open()
        response = await card.post(card.body({"price": 2440}))
        assert response.status_code == 202
        # The owner types while the send waits: their message folds into its Run's window.
        typed = await fixture.request(
            "POST", f"/threads/{card.thread['id']}/messages", {"content": "اشترِ الآن"}
        )
        assert typed["run_ids"] == response.json()["run_ids"]
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, response.json()["run_ids"][0])
            assert run is not None and run.input_seq >= typed["message"]["seq"]
            # Even so, a Run a card's send started has no owner words at all.
            assert await owner_typed_message(session, run) is None
            assert await owner_message_id(session, run) is None
            # A v1 follow-up tap is stored as card words at write time.
            thread = await session.get(ThreadRow, card.thread["id"], with_for_update=True)
            assert thread is not None
            v1 = MessageRow(
                thread_id=thread.id,
                agent_id=card.agent["id"],
                role="assistant",
                seq=thread.next_seq,
                content="x",
                rich_content={
                    "parts": [
                        {
                            "type": "ui",
                            "document": {
                                "root": {"action": {"kind": "follow_up", "text": "اشرح لي النتيجة"}}
                            },
                        }
                    ]
                },
            )
            thread.next_seq += 1
            session.add(v1)
        tap = await fixture.request(
            "POST", f"/threads/{card.thread['id']}/messages", {"content": "اشرح لي النتيجة"}
        )
        assert tap["message"]["origin"] == "ui_follow_up"
        typed = await fixture.request(
            "POST", f"/threads/{card.thread['id']}/messages", {"content": "اشرح لي بالتفصيل"}
        )
        assert typed["message"]["origin"] == "owner"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_watch_created_by_a_submission_wakes_tainted() -> None:
    from lonora_db.schema import RunRow
    from test_proactive_wakes import call, retire, simulation

    fixture = await open_fixture()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        card = await Card(fixture).open()
        response = await card.post(card.body({"price": 2450}))
        assert response.status_code == 202
        submit_run = {
            "id": response.json()["run_ids"][0],
            "agent_id": card.agent["id"],
            "thread_id": card.thread["id"],
        }
        context = await fixture.lease(submit_run)
        created = await call(
            context,
            "watch_create",
            account_id=connection,
            symbol="XAUUSD",
            condition="above",
            level="2450",
            prompt="Tell the owner gold crossed 2450.",
        )
        from lonora_db.genui_taint import row_taint

        async with fixture.runtime.db.sessions() as session:
            run = await session.get(RunRow, submit_run["id"])
            assert run is not None
            # The ledger keeps the taint; the watch's own state holds no copy to rewrite.
            taint = await row_taint(session, "watch", created["id"])
            assert taint == run.model_metadata["ui_submit_origin"]
    finally:
        await retire(fixture, connection)
        await fixture.close()


def test_every_owner_words_read_uses_the_helper_or_reads_origin() -> None:
    """docs/genui.md §7: every query of user messages either goes through ``owner_words``, reads
    ``origin`` or sits on this reviewed allowlist with its reason."""
    root = Path(__file__).parent.parent
    allowed = {
        # The idempotency backfill pairs an old message with its own runs; no authority.
        "packages/db/src/lonora_db/messages.py": "nonce backfill",
        "packages/db/src/lonora_db/conversation_locale.py": "reply language evidence only",
        "packages/db/src/lonora_db/steering.py": "pending-steering existence, not words",
        # The id of the message a run answers, to refuse retry after an edit. Not its words.
        "packages/db/src/lonora_db/run_retry.py": "edited-source existence, not words",
        # The id of the message this turn answers, so a reaction can land. Not its words.
        "packages/tools/src/lonora_tools/message.py": "reaction target id, not owner words",
        "packages/agent-runtime/src/lonora_agent/context/skills.py": "reads origin",
        "packages/memory/src/lonora_memory/conversation.py": "reads origin",
        "packages/tools/src/lonora_tools/trade.py": "reads origin",
        "packages/tools/src/lonora_tools/owner_actions.py": "reads origin",
        "packages/tools/src/lonora_tools/models.py": "reads origin",
    }
    offenders: list[str] = []
    for path in [*root.glob("packages/*/src/**/*.py"), *root.glob("apps/*/src/**/*.py")]:
        text = path.read_text()
        if 'MessageRow.role == "user"' not in text:
            continue
        relative = str(path.relative_to(root))
        if relative in allowed:
            if allowed[relative] == "reads origin":
                assert "origin" in text, relative
            continue
        if "owner_words" in text or "MessageRow.origin" in text:
            continue
        offenders.append(relative)
    assert offenders == [], offenders


@pytest.mark.asyncio
async def test_the_cards_account_is_named_beyond_the_bounded_account_list() -> None:
    """With more enabled accounts than ``enabled_accounts`` returns, the card's own
    account is still read and named; an unnamed one is still refused."""
    from lonora_core.user_error import LonoraError
    from lonora_db.genui_submit import identity_names
    from lonora_db.schema import BrokerSessionRow
    from test_proactive_wakes import retire, simulation

    fixture = await open_fixture()
    connections: list[str] = []
    try:
        connections += [await simulation(fixture, []) for _ in range(10)]
        last = connections[-1]
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(BrokerSessionRow, last, with_for_update=True)
            assert row is not None
            owner_id = row.owner_id
            row.state = {
                **row.state,
                "broker_identity": {
                    "broker": "Simulation",
                    "login": "12345678",
                    "server": "Demo",
                    "connection_version": row.version,
                },
            }
        async with fixture.runtime.db.sessions() as session:
            names = await identity_names(
                session, owner_id, {}, "alert.create", {"account_id": last}
            )
            assert names["account_id"] == "Simulation · 12345678 · Demo"
            with pytest.raises(LonoraError) as refused:
                await identity_names(
                    session, owner_id, {}, "alert.create", {"account_id": connections[0]}
                )
            assert refused.value.code == "ui_submit_account_unnamed"
    finally:
        await retire(fixture, *connections)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_send_that_ran_is_never_marked_and_clients_learn_it_started() -> None:
    """U1: the start is pushed to clients (``message.updated`` with ``started_at``), and a
    Run that started and finished leaves no never-run mark, so its card stays locked."""
    from lonora_db.genui_submit import mark_submit_started
    from lonora_db.schema import EventRow, RunRow
    from sqlalchemy import select

    fixture = await open_fixture()
    try:
        card = await Card(fixture).open()
        response = await card.post(card.body({"price": 2450}))
        assert response.status_code == 202
        submit = response.json()["message"]
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, response.json()["run_ids"][0], with_for_update=True)
            assert run is not None
            await mark_submit_started(session, run)
            run.status = "completed"
        async with fixture.runtime.db.sessions() as session:
            events = list(
                await session.scalars(
                    select(EventRow).where(
                        EventRow.thread_id == card.thread["id"],
                        EventRow.kind == "message.updated",
                    )
                )
            )
        assert any(
            e.payload.get("id") == submit["id"] and e.payload["ui_submit"].get("started_at")
            for e in events
        )
        page = await fixture.request("GET", f"/threads/{card.thread['id']}/messages")
        shown = next(m for m in page if m["id"] == submit["id"])
        assert shown.get("ui_mark") is None and "mark" not in shown["ui_submit"]
        assert next(m for m in page if m["id"] == card.message_id)["ui_lock"]["1"]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_an_owner_message_folded_into_a_queued_send_survives_its_edit() -> None:
    """The owner types while a card's send waits: their message joins that queued Run.
    «تعديل» cancels the send, never the owner's words: they get a normal owner Run."""
    from lonora_db.genui_taint import SUBMIT

    fixture = await open_fixture()
    try:
        card = await Card(fixture).open()
        response = await card.post(card.body({"price": 2460}))
        assert response.status_code == 202
        submit_run = response.json()["run_ids"][0]
        typed = await fixture.request(
            "POST", f"/threads/{card.thread['id']}/messages", {"content": "وأيضًا راقب الفضة"}
        )
        assert typed["run_ids"] == [submit_run]  # folded into the queued send's Run
        await fixture.request(
            "POST", f"/threads/{card.thread['id']}/messages/{card.message_id}/ui-state/1/unlock"
        )
        queued = [r for r in await runs(fixture, card.thread["id"]) if r.status == "queued"]
        assert len(queued) == 1 and SUBMIT not in queued[0].model_metadata
        assert queued[0].input_seq >= typed["message"]["seq"]
    finally:
        await fixture.close()


@pytest.mark.parametrize("language", ["ar", "en"])
@pytest.mark.asyncio
async def test_alert_off_names_the_watch_in_the_conversations_language(language: str) -> None:
    """«إيقاف التنبيه» on a receipt: the bubble names the watch in the watch list's own
    words, in the conversation's language (review)."""
    from lonora_db.schema import OwnerProfileRow
    from test_proactive_wakes import call, retire, simulation

    fixture = await open_fixture()
    connection = ""
    previous: str | None = None
    try:
        connection = await simulation(fixture, [])
        card = await Card(fixture).start()
        context = await fixture.lease(await fixture.run(card.agent, card.thread))
        watch = await call(
            context,
            "watch_create",
            account_id=connection,
            symbol="XAUUSD",
            condition="above",
            level="2400",
            prompt="Tell the owner.",
        )
        receipt = "\n".join(
            [
                '{"v":2,"kind":"summary","title":"تنبيه فعّال","icon":"check"}',
                '{"type":"Button","label":"إيقاف التنبيه","icon":"bellOff","action":'
                '{"do":"send","intent":"alert.off","data":{"watch_id":"' + watch["id"] + '"}}}',
                '{"why":"w","fallback":"التنبيه فعّال."}',
            ]
        )
        created = [
            ModelMessage(
                role="assistant",
                content="",
                tool_calls=[ToolCall(id="w1", name="watch_create", arguments={})],
            ),
            ModelMessage(role="tool", tool_call_id="w1", content=json.dumps({"id": watch["id"]})),
        ]
        async with fixture.runtime.db.sessions() as session, session.begin():
            profile = await session.get(OwnerProfileRow, fixture.owner)
            if profile is None:
                profile = OwnerProfileRow(owner_id=fixture.owner)
                session.add(profile)
            previous = profile.reply_language
            profile.reply_language = language
        await card.place(receipt, created)
        response = await card.post(card.body({}, path="0"))
        assert response.status_code == 202, response.text
        message = response.json()["message"]
        assert message["ui_submit"]["intent"] == "alert.off"
        # The watch list's own words (watchCondition), in the conversation's language.
        expected = {
            "ar": "أوقف تنبيه \u2068XAUUSD\u2069 فوق \u20682400\u2069",
            "en": "Stop the alert \u2068XAUUSD\u2069 above \u20682400\u2069",
        }[language]
        assert message["content"] == expected
    finally:
        async with fixture.runtime.db.sessions() as session, session.begin():
            profile = await session.get(OwnerProfileRow, fixture.owner)
            if profile is not None:
                profile.reply_language = previous
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_the_compiler_names_the_cards_account_beyond_the_bounded_list() -> None:
    """The compile-side twin of the submit check: with ten accounts, the account this
    request read is named by a direct, owner-checked read wherever it sits (review)."""
    from types import SimpleNamespace

    from lonora_agent.visual_response import VisualReplyProjector
    from lonora_db.schema import BrokerSessionRow
    from test_proactive_wakes import retire, simulation

    fixture = await open_fixture()
    connections: list[str] = []
    try:
        connections += [await simulation(fixture, []) for _ in range(10)]
        named, unnamed = connections[-1], connections[-2]
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(BrokerSessionRow, named, with_for_update=True)
            assert row is not None
            row.state = {
                **row.state,
                "broker_identity": {
                    "broker": "Simulation",
                    "login": "12345678",
                    "server": "Demo",
                    "connection_version": row.version,
                },
            }
        card = await Card(fixture).start()
        reads = [
            ModelMessage(
                role="assistant",
                content="",
                tool_calls=[
                    ToolCall(id=f"q{i}", name="market_quote", arguments={"account_id": account})
                    for i, account in enumerate([named, unnamed])
                ],
            )
        ]
        context = SimpleNamespace(
            db=fixture.runtime.db, owner_id=fixture.owner, agent_id=card.agent["id"], thread_id="t"
        )
        scope = await VisualReplyProjector(context, reads).agent_scope()  # type: ignore[arg-type]
        assert scope.several_accounts and scope.named_accounts == frozenset({named})
    finally:
        await retire(fixture, *connections)
        await fixture.close()


@pytest.mark.asyncio
async def test_an_owner_message_steered_into_a_leased_send_survives_its_edit() -> None:
    """Review round 4: the send was leased (not yet running) when the owner typed, so their
    message became a steering row; «تعديل» still re-queues it."""
    fixture = await open_fixture()
    try:
        card = await Card(fixture).open()
        response = await card.post(card.body({"price": 2470}))
        assert response.status_code == 202
        submit_run = response.json()["run_ids"][0]
        from lonora_db.schema import RunRow

        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, submit_run, with_for_update=True)
            assert run is not None
            run.status = "leased"
        typed = await fixture.request(
            "POST", f"/threads/{card.thread['id']}/messages", {"content": "وأيضًا الفضة"}
        )
        assert typed["run_ids"] == [submit_run]
        await fixture.request(
            "POST", f"/threads/{card.thread['id']}/messages/{card.message_id}/ui-state/1/unlock"
        )
        queued = [r for r in await runs(fixture, card.thread["id"]) if r.status == "queued"]
        assert len(queued) == 1 and queued[0].id != submit_run
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_an_edit_never_duplicates_an_owner_message_another_run_answers() -> None:
    """The claim window (rule W) may reach owner messages another Run answers; «تعديل»
    re-queues only what the send itself took, so nothing is answered twice."""
    from lonora_db.schema import RunRow

    fixture = await open_fixture()
    try:
        card = await Card(fixture).open()
        earlier = await fixture.run(card.agent, card.thread)  # the oldest active Run
        response = await card.post(card.body({"price": 2480}))
        assert response.status_code == 202
        submit_run = response.json()["run_ids"][0]
        typed = await fixture.request(
            "POST", f"/threads/{card.thread['id']}/messages", {"content": "ما رأيك؟"}
        )
        assert typed["run_ids"] == [earlier["id"]]  # folded into the earlier Run, not the send
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, submit_run, with_for_update=True)
            assert run is not None
            run.input_seq = typed["message"]["seq"]  # as rule W raises it at claim
        await fixture.request(
            "POST", f"/threads/{card.thread['id']}/messages/{card.message_id}/ui-state/1/unlock"
        )
        queued = [r.id for r in await runs(fixture, card.thread["id"]) if r.status == "queued"]
        assert queued == [earlier["id"]]
    finally:
        await fixture.close()
