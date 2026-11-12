"""What a paused agent does (mandate 4.7.1, 3.2.5).

A paused agent takes no new work: its routines, watches and timers are held, and only the
owner's direct message or a broker event on its own positions and pending orders starts a
run of it. Through the door it sends only risk-reducing requests, in either mode. Runs on
the real migrated PostgreSQL schema and the simulation broker (skipped without
``LONORA_DATABASE_URL``).
"""

from datetime import timedelta
from uuid import uuid4

import pytest
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradingControl
from lonora_core.user_error import LonoraError
from test_proactive_wakes import call, database, retire, simulation


def test_only_the_owners_message_and_its_own_broker_events_run_while_paused() -> None:
    from lonora_db.pauses import runs_while_paused

    assert runs_while_paused("user", {})
    # In a group, only a run the owner addressed to it; never the group's fallback.
    assert runs_while_paused("group", {"owner_addressed": True})
    assert not runs_while_paused("group", {})
    assert runs_while_paused("broker_event", {})
    # Activity on tickets it does not own is an observe-only wake: not its own.
    assert not runs_while_paused("broker_event", {"authority": "observe_only"})
    for trigger in ("routine", "watch", "tickets", "peer", "follow_up", "subagent", "webhook"):
        assert not runs_while_paused(trigger, {}), trigger


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
    from lonora_trading.controls import read_controls, save_controls
    from sqlalchemy import func, select

    fixture = await Fixture().open()
    original = await read_controls(fixture.runtime.db)
    connection = ""
    try:
        connection = await simulation(fixture, [])
        await save_controls(fixture.runtime.db, TradingControl(enabled=True))
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

        # The owner's direct message starts a new run of the paused agent; a held run
        # in the conversation never takes the owner's words.
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
        assert len(sent["run_ids"]) == 1 and held_id not in sent["run_ids"], sent
        async with fixture.runtime.db.sessions() as session:
            run = await session.get(RunRow, sent["run_ids"][0])
            assert run is not None and run.agent_id == gold["id"] and run.trigger == "user"
            assert run.status == "queued"
            assert await session.scalar(
                select(RunRow.id).where(RunRow.id == run.id, claimable_while_paused())
            )
            assert not await session.scalar(
                select(RunRow.id).where(RunRow.id == held_id, claimable_while_paused())
            )
            # Settle both, so no later test claims them.
            for run_id in (run.id, held_id):
                row = await session.get(RunRow, run_id)
                assert row is not None
                row.status = "cancelled"
            await session.commit()
    finally:
        await save_controls(fixture.runtime.db, original)
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
