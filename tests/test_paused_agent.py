"""What a paused agent does (mandate 4.7.1).

A paused agent takes no new work: its routines, watches and timers are held, the owner's
messages to it are kept and start no run, and only a broker event on its own positions
and pending orders starts a run of it. Through the door it sends only risk-reducing
requests, in either mode. Runs on the real migrated PostgreSQL schema and the simulation
broker (skipped without ``LONORA_DATABASE_URL``).
"""

from datetime import timedelta
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


@pytest.mark.asyncio
@pytest.mark.parametrize("by", ["owner", "lonora"])
async def test_pausing_withdraws_the_agents_pending_trade_approval_cards(by: str) -> None:
    """10.3.1.3, 4.7.1: a paused agent sends no new risk, so its pending Trade Approval
    card ends on the pause: withdrawn, never executed, and no longer approvable, so the
    owner never spends an Approve the door would refuse. The run waiting on it is held
    while paused and, once resumed, reads why the card ended and decides again. The
    owner's pause and Lonora's withdraw it alike."""
    database()
    from check_streaming import Fixture
    from lonora_db.pauses import claimable_while_paused
    from lonora_db.personal_agent import ensure_personal_agent
    from lonora_db.schema import RunRow, TradeApprovalRow, TradingJournalRow
    from lonora_db.supervision import control_work
    from sqlalchemy import select
    from test_mandate_card import agent_run, same_call

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        agent = await fixture.agent("Paused card " + by, supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        entry = {
            "action": "buy",
            "account_id": connection,
            "symbol": "XAUUSD",
            "volume": "0.1",
            "tolerance": "2",
            "reason": "Fixture entry",
        }
        asked = await same_call(context, entry)
        assert asked.get("_runtime_wait") and asked.get("approval_id"), asked
        async with fixture.runtime.db.sessions() as session, session.begin():
            # The runtime parks a run that waits on a card.
            waiting = await session.get(RunRow, context.lease.run_id, with_for_update=True)
            assert waiting is not None
            waiting.status = "waiting_input"
        if by == "owner":
            await fixture.request("PATCH", f"/agents/{agent['id']}", {"paused": True})
        else:
            async with fixture.runtime.db.sessions() as session, session.begin():
                lonora = await ensure_personal_agent(session, fixture.owner)
                await control_work(
                    session,
                    fixture.owner,
                    actor_id=lonora.id,
                    agent_id=agent["id"],
                    kind="agent",
                    target_id=None,
                    action="pause",
                    owner_message_id=None,
                    run_id=None,
                )
        async with fixture.runtime.db.sessions() as session:
            card = await session.get(TradeApprovalRow, asked["approval_id"])
            assert card is not None and card.status == "withdrawn"
            assert card.validity["withdrawn_by"] == "pause"
            run = await session.get(RunRow, context.lease.run_id)
            assert run is not None and run.status == "queued"
            # Woken to read the outcome, but held while the agent is paused.
            assert not await session.scalar(
                select(RunRow.id).where(RunRow.id == run.id, claimable_while_paused())
            )
        late = await fixture.client.post(
            f"/api/trading/approvals/{asked['approval_id']}/decision", json={"decision": "approve"}
        )
        assert late.status_code == 409, late.text
        await fixture.request("PATCH", f"/agents/{agent['id']}", {"paused": False})
        context = await fixture.lease({"id": context.lease.run_id, **agent_run(context)})
        answer = await same_call(context, entry)
        assert answer.get("status") == "withdrawn", answer
        assert answer["recovery"].startswith("You were paused"), answer["recovery"]
        assert "(Ask)" in answer["recovery"], answer["recovery"]
        async with fixture.runtime.db.sessions() as session:
            sent = await session.scalar(
                select(TradingJournalRow.operation_id).where(
                    TradingJournalRow.owner_id == fixture.owner,
                    TradingJournalRow.account_id == connection,
                )
            )
        assert sent is None, "a paused agent's card was executed"
    finally:
        await retire(fixture, connection)
        await fixture.close()
