"""What a paused agent does (mandate 4.7.1).

A paused agent takes no new work: its routines, watches and timers are held, the owner's
messages to it are kept and start no run, and only a broker event on its own positions
and pending orders starts a run of it. Through the door it sends only risk-reducing
requests, in either mode, and its pending Trade Approval card stays pending until the
resume. Runs on the real migrated PostgreSQL schema and the simulation broker (skipped
without ``LONORA_DATABASE_URL``).
"""

from datetime import timedelta
from typing import Any
from uuid import uuid4

import pytest
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from test_proactive_wakes import call, database, retire, simulation


def test_only_its_own_broker_events_run_while_paused() -> None:
    from lonora_db.pauses import runs_while_paused

    own = {"broker_event_ids": ["e1"], "account_id": "a"}
    assert runs_while_paused("broker_event", own)
    # Activity on tickets it does not own is an observe-only wake: not its own.
    assert not runs_while_paused("broker_event", {**own, "authority": "observe_only"})
    # Lonora's system alerts (broker health, an uncertain operation) are not its tickets.
    assert not runs_while_paused("broker_event", {"system_alert": "broker_degraded"})
    assert not runs_while_paused("broker_event", {})
    # The owner's messages, addressed or not, start no run of it.
    for trigger in ("user", "group", "routine", "watch", "tickets", "peer", "follow_up"):
        assert not runs_while_paused(trigger, {}), trigger
    assert not runs_while_paused("group", {"owner_addressed": True})


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["full", "ask"])
async def test_a_paused_agent_wakes_for_its_ticket_closes_it_and_adds_no_risk(mode: str) -> None:
    database()
    from check_streaming import Fixture
    from lonora_contracts.broker_activity import BrokerActivity
    from lonora_contracts.routines import RoutineCreate
    from lonora_contracts.runs import RunRequest
    from lonora_db.pauses import claimable_while_paused
    from lonora_db.routines import create_routine, due_query
    from lonora_db.runs import create_run
    from lonora_db.schema import RoutineRow, RunRow, TradeApprovalRow
    from lonora_db.trading_mode import set_trading_mode
    from lonora_trading.broker_recovery import wake_for_activity
    from sqlalchemy import func, select

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        gold = await fixture.agent("Paused " + mode, supervised=True)
        thread = await fixture.conversation(gold)
        async with fixture.runtime.db.sessions() as session, session.begin():
            await set_trading_mode(session, fixture.owner, gold["id"], "full", by="owner_tap")
        context = await fixture.lease(await fixture.run(gold, thread))
        entry = {"action": "buy", "account_id": connection, "symbol": "XAUUSD", "stop_loss": "95"}
        opened = await call(context, "trade_execute", **entry, volume="0.2")
        assert opened.get("status") == "confirmed", opened
        if mode == "ask":
            async with fixture.runtime.db.sessions() as session, session.begin():
                await set_trading_mode(session, fixture.owner, gold["id"], "ask", by="agent")
        async with fixture.runtime.db.sessions() as session, session.begin():
            routine = await create_routine(
                session,
                fixture.owner,
                gold["id"],
                RoutineCreate(prompt="Scan gold", interval_seconds=3600),
            )
            routine.next_run_at = utcnow() - timedelta(minutes=1)
            routine_id = routine.id

        await fixture.request("PATCH", f"/agents/{gold['id']}", {"paused": True})

        # Its routine is held, and no other work of it starts.
        async with fixture.runtime.db.sessions() as session:
            due = await session.scalars(due_query(utcnow()).where(RoutineRow.id == routine_id))
            assert list(due) == []
        with pytest.raises(LonoraError, match="agent_paused"):
            async with fixture.runtime.db.sessions() as session, session.begin():
                await create_run(
                    session,
                    fixture.owner,
                    RunRequest(
                        thread_id=thread["id"], agent_id=gold["id"], trigger="routine", prompt="x"
                    ),
                )

        # A broker event on its own ticket wakes it with its normal authority.
        broker = await fixture.runtime.services(fixture.owner).brokers.get(
            fixture.owner, connection
        )
        (position,) = await broker.positions()
        async with fixture.runtime.db.sessions() as session, session.begin():
            await wake_for_activity(
                session,
                fixture.owner,
                connection,
                7,
                [
                    BrokerActivity(
                        id=str(uuid4()),
                        account_id=connection,
                        symbol="XAUUSD",
                        ticket=position.id,
                        resource="position",
                        change="modified",
                        origin="external",
                        observed_at=utcnow(),
                        current=position,
                        agent_id=gold["id"],
                    )
                ],
            )
        async with fixture.runtime.db.sessions() as session:
            (woke,) = list(
                await session.scalars(
                    select(RunRow).where(
                        RunRow.agent_id == gold["id"], RunRow.trigger == "broker_event"
                    )
                )
            )
            assert "authority" not in woke.model_metadata
            assert "You are paused" in woke.prompt
            # The wake is claimable while the agent is paused.
            assert await session.scalar(
                select(RunRow.id).where(RunRow.id == woke.id, claimable_while_paused())
            )
        wake = await fixture.lease(
            {"id": woke.id, "agent_id": gold["id"], "thread_id": woke.thread_id}
        )

        # New risk is refused, and no card is raised for it.
        with pytest.raises(LonoraError, match="agent_paused"):
            await call(wake, "trade_execute", **entry, volume="0.1", tolerance="1", reason="Add on")
        # It closes its own position through the door.
        closed = await call(
            wake,
            "trade_execute",
            action="close_position",
            account_id=connection,
            symbol="XAUUSD",
            position_id=position.id,
        )
        assert closed.get("status") == "confirmed", closed
        assert await broker.positions() == []
        async with fixture.runtime.db.sessions() as session:
            cards = await session.scalar(
                select(func.count())
                .select_from(TradeApprovalRow)
                .where(TradeApprovalRow.agent_id == gold["id"])
            )
        assert cards == 0

        # The door itself refuses the paused agent's new risk, whatever the tool did first.
        from decimal import Decimal

        from lonora_contracts.trading import TradeRequest
        from lonora_trading.agent_permission import require_operation_permission

        async with fixture.runtime.db.sessions() as session:
            woken = await session.get(RunRow, woke.id)
            assert woken is not None
            for reducing in (None, False):
                with pytest.raises(LonoraError, match="agent_paused"):
                    await require_operation_permission(
                        session,
                        fixture.owner,
                        woken,
                        TradeRequest(
                            account_id=connection,
                            action="buy",
                            symbol="XAUUSD",
                            volume=Decimal("0.1"),
                        ),
                        None,
                        reducing=reducing,
                    )

        # The owner's message to the paused agent is kept and starts no run (4.7.1); a
        # held run in the conversation never takes the owner's words either.
        async with fixture.runtime.db.sessions() as session, session.begin():
            for run_id in (context.lease.run_id, woke.id):
                row = await session.get(RunRow, run_id)
                assert row is not None
                row.status = "completed"
            held = RunRow(
                thread_id=thread["id"],
                agent_id=gold["id"],
                trigger="follow_up",
                input_seq=0,
            )
            session.add(held)
            await session.flush()
            held_id = held.id
        sent = await fixture.request(
            "POST", f"/threads/{thread['id']}/messages", {"content": "How is gold?"}
        )
        assert sent["run_ids"] == [] and sent["message"]["content"] == "How is gold?", sent
        async with fixture.runtime.db.sessions() as session:
            runs = list(
                await session.scalars(
                    select(RunRow.id).where(
                        RunRow.thread_id == thread["id"],
                        RunRow.agent_id == gold["id"],
                        RunRow.status == "queued",
                    )
                )
            )
            assert runs == [held_id], runs
            assert not await session.scalar(
                select(RunRow.id).where(RunRow.id == held_id, claimable_while_paused())
            )
            row = await session.get(RunRow, held_id)
            assert row is not None
            # Settle it, so no later test claims it.
            row.status = "cancelled"
            await session.commit()
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_card_ending_notice_waits_for_the_resume_instead_of_failing() -> None:
    """A Trade Approval card of a paused agent can still be withdrawn or drift: the notice
    run is queued and held until the agent is resumed, so the mode change or the drift
    that ended the card is never rolled back."""
    database()
    from check_streaming import Fixture
    from lonora_contracts.runs import RunRequest
    from lonora_db.pauses import claimable_while_paused
    from lonora_db.runs import create_run
    from lonora_db.schema import RunRow
    from lonora_db.trade_approvals import WITHDRAWN_TRIGGER
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        gold = await fixture.agent("Paused card")
        thread = await fixture.conversation(gold)
        await fixture.request("PATCH", f"/agents/{gold['id']}", {"paused": True})
        request = RunRequest(
            thread_id=thread["id"], agent_id=gold["id"], trigger=WITHDRAWN_TRIGGER, prompt="x"
        )
        with pytest.raises(LonoraError, match="agent_paused"):
            async with fixture.runtime.db.sessions() as session, session.begin():
                await create_run(session, fixture.owner, request)
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await create_run(session, fixture.owner, request, held_while_paused=True)
            assert run.status == "queued"
            assert not await session.scalar(
                select(RunRow.id).where(RunRow.id == run.id, claimable_while_paused())
            )
            run.status = "cancelled"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_system_alert_wake_queued_before_the_pause_is_held() -> None:
    """Lonora's broker-health and uncertain-operation wakes are broker_event runs too,
    but not about its own tickets: one queued before the owner paused Lonora is never
    claimed while it is paused (4.7.1), and runs once it is resumed."""
    database()
    from check_streaming import Fixture
    from lonora_contracts.domain import ThreadCreate
    from lonora_contracts.runs import RunRequest
    from lonora_db.pauses import claimable_while_paused
    from lonora_db.personal_agent import ensure_personal_agent
    from lonora_db.runs import create_run
    from lonora_db.schema import RunRow
    from lonora_db.threads import create_thread
    from sqlalchemy import select

    fixture = await Fixture().open()
    lonora_id = ""
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            lonora = await ensure_personal_agent(session, fixture.owner)
            lonora_id = lonora.id
            work = await create_thread(
                session, fixture.owner, ThreadCreate(agent_id=lonora.id), purpose="work"
            )
            alert = await create_run(
                session,
                fixture.owner,
                RunRequest(
                    thread_id=work.id,
                    agent_id=lonora.id,
                    trigger="broker_event",
                    prompt="The broker connection is degraded.",
                    metadata={"system_alert": "broker_degraded", "attention_id": "x"},
                ),
            )
            alert_id = alert.id
        await fixture.request("PATCH", f"/agents/{lonora_id}", {"paused": True})
        async with fixture.runtime.db.sessions() as session:
            assert not await session.scalar(
                select(RunRow.id).where(RunRow.id == alert_id, claimable_while_paused())
            )
        with pytest.raises(LonoraError, match="agent_paused"):
            async with fixture.runtime.db.sessions() as session, session.begin():
                await create_run(
                    session,
                    fixture.owner,
                    RunRequest(
                        thread_id=work.id,
                        agent_id=lonora_id,
                        trigger="broker_event",
                        prompt="x",
                        metadata={"system_alert": "broker_degraded"},
                    ),
                )
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, alert_id)
            assert row is not None
            row.status = "cancelled"
    finally:
        if lonora_id:
            await fixture.request("PATCH", f"/agents/{lonora_id}", {"paused": False})
        await fixture.close()


async def own_wake(fixture: Any, agent_id: str, conversation_id: str) -> str:
    """A wake for broker activity on the agent's own tickets, in its work thread and
    reporting to its conversation (``wake_for_activity``), made before the pause."""
    from lonora_contracts.domain import ThreadCreate
    from lonora_contracts.runs import RunRequest
    from lonora_db.runs import create_run
    from lonora_db.threads import create_thread

    async with fixture.runtime.db.sessions() as session, session.begin():
        work = await create_thread(
            session, fixture.owner, ThreadCreate(agent_id=agent_id), purpose="work"
        )
        run = await create_run(
            session,
            fixture.owner,
            RunRequest(
                thread_id=work.id,
                agent_id=agent_id,
                trigger="broker_event",
                prompt="Broker activity on positions or orders you opened.",
                metadata={"origin_thread_id": conversation_id, "broker_event_ids": ["e1"]},
            ),
        )
        return run.id


@pytest.mark.asyncio
async def test_a_paused_agents_card_stays_pending_and_approve_waits_for_the_resume() -> None:
    """10.3.1.3 names no pause among the ways a card ends, and a paused agent sends no
    new risk (4.7.1): the card stays pending, the owner's Approve is refused with a true
    line until the resume, and a wake whose card was approved before the pause is held,
    so that Approve is kept for the resume instead of spent on the door's refusal."""
    database()
    from check_streaming import Fixture
    from lonora_db.pauses import claimable_while_paused
    from lonora_db.schema import RunRow, TradeApprovalRow, TradingJournalRow
    from sqlalchemy import select
    from test_mandate_card import same_call

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        agent = await fixture.agent("Paused card", supervised=True)
        thread = await fixture.conversation(agent)
        wake_id = await own_wake(fixture, agent["id"], thread["id"])
        async with fixture.runtime.db.sessions() as session:
            wake = await session.get(RunRow, wake_id)
            assert wake is not None
            run = {"id": wake_id, "agent_id": agent["id"], "thread_id": wake.thread_id}
        context = await fixture.lease(run)
        entry = {
            "action": "buy",
            "account_id": connection,
            "symbol": "XAUUSD",
            "volume": "0.1",
            "tolerance": "5",
            "reason": "Fixture entry",
        }
        asked = await same_call(context, entry)
        assert asked.get("_runtime_wait") and asked.get("approval_id"), asked
        approval = f"/api/trading/approvals/{asked['approval_id']}/decision"

        async def park() -> None:
            # The runtime parks a run that waits on a card.
            async with fixture.runtime.db.sessions() as session, session.begin():
                waiting = await session.get(RunRow, wake_id, with_for_update=True)
                assert waiting is not None
                waiting.status = "waiting_input"

        await park()
        await fixture.request("PATCH", f"/agents/{agent['id']}", {"paused": True})
        refused = await fixture.client.post(approval, json={"decision": "approve"})
        assert refused.status_code == 409, refused.text
        assert refused.json()["code"] == "trade_approval_agent_paused", refused.text
        async with fixture.runtime.db.sessions() as session:
            card = await session.get(TradeApprovalRow, asked["approval_id"])
            assert card is not None and card.status == "pending"
            held = await session.get(RunRow, wake_id)
            assert held is not None and held.status == "waiting_input"

        # Resumed, the owner approves; paused again before it is sent, the wake waits.
        await fixture.request("PATCH", f"/agents/{agent['id']}", {"paused": False})
        approved = await fixture.client.post(approval, json={"decision": "approve"})
        assert approved.status_code == 200, approved.text
        await fixture.request("PATCH", f"/agents/{agent['id']}", {"paused": True})
        async with fixture.runtime.db.sessions() as session:
            card = await session.get(TradeApprovalRow, asked["approval_id"])
            assert card is not None and card.status == "approved"
            queued = await session.get(RunRow, wake_id)
            assert queued is not None and queued.status == "queued"
            assert not await session.scalar(
                select(RunRow.id).where(RunRow.id == wake_id, claimable_while_paused())
            )
            sent = await session.scalar(
                select(TradingJournalRow.operation_id).where(
                    TradingJournalRow.owner_id == fixture.owner,
                    TradingJournalRow.account_id == connection,
                )
            )
        assert sent is None, "a paused agent's approved card was sent"

        # Once resumed, the kept Approve is sent.
        await fixture.request("PATCH", f"/agents/{agent['id']}", {"paused": False})
        context = await fixture.lease(run)
        done = await same_call(context, entry)
        assert done.get("status") == "confirmed", done
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("answer", ["tap", "typed"])
async def test_no_answer_reaches_a_paused_agents_wake_until_it_is_resumed(answer: str) -> None:
    """A paused agent takes no new work and the owner's messages to it start nothing
    (4.7.1): a question its own broker wake asked is answered by neither form while it
    is paused (a tapped choice is refused, a typed reply or next message is kept), and the
    question stays open. Once resumed, either form reaches the wake."""
    database()
    from check_streaming import Fixture
    from lonora_db.schema import MessageRow, RunRow, ThreadRow

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Paused question " + answer)
        thread = await fixture.conversation(agent)
        wake_id = await own_wake(fixture, agent["id"], thread["id"])
        choice = {"id": "close", "label": "Close it"}
        async with fixture.runtime.db.sessions() as session, session.begin():
            conversation = await session.get(ThreadRow, thread["id"], with_for_update=True)
            assert conversation is not None
            question = MessageRow(
                thread_id=conversation.id,
                agent_id=agent["id"],
                seq=conversation.next_seq,
                role="assistant",
                content="Gold hit its stop. Close the rest?",
            )
            conversation.next_seq += 1
            session.add(question)
            await session.flush()
            question_id = question.id
            wake = await session.get(RunRow, wake_id, with_for_update=True)
            assert wake is not None
            # The wake's question, copied into the conversation it reports to (11.6).
            wake.status = "waiting_input"
            wake.execution_state = {
                "pending_input_request": {"id": "q1"},
                "input_requests": [
                    {
                        "id": "q1",
                        "question": question.content,
                        "choices": [choice],
                        "run_id": wake_id,
                        "message_id": question_id,
                        "thread_id": conversation.id,
                        "source_message_id": question_id,
                        "status": "pending",
                        "selected_choice_id": None,
                        "answer_message_id": None,
                    }
                ],
            }
        messages = f"/threads/{thread['id']}/messages"
        tap = {
            "content": choice["label"],
            "reply_to": question_id,
            "input_answer": {"run_id": wake_id, "question_id": "q1", "choice_id": "close"},
        }

        async def still_open() -> None:
            async with fixture.runtime.db.sessions() as session:
                row = await session.get(RunRow, wake_id)
                assert row is not None and row.status == "waiting_input"
                assert row.execution_state["input_requests"][0]["status"] == "pending"

        await fixture.request("PATCH", f"/agents/{agent['id']}", {"paused": True})
        refused = await fixture.client.post("/api" + messages, json=tap)
        assert refused.status_code == 409 and refused.json()["code"] == "agent_paused", refused.text
        await still_open()
        # The next message would answer the question (it is the last one there), and a
        # reply to it always would: while paused, neither does.
        for typed in ({"content": "close it"}, {"content": "close it", "reply_to": question_id}):
            kept = await fixture.request("POST", messages, typed)
            assert kept["run_ids"] == [] and kept["message"]["content"] == "close it", kept
            await still_open()

        await fixture.request("PATCH", f"/agents/{agent['id']}", {"paused": False})
        resumed = await fixture.request(
            "POST",
            messages,
            tap if answer == "tap" else {"content": "close it", "reply_to": question_id},
        )
        assert resumed["run_ids"] == [wake_id], resumed
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, wake_id, with_for_update=True)
            assert row is not None and row.status == "queued"
            assert row.execution_state["input_requests"][0]["status"] == "answered"
            # Settle it, so no later test claims it.
            row.status = "cancelled"
    finally:
        await fixture.close()
