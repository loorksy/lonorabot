"""The agent's judgment label (mandate 5.5.3, 14.3.9).

"Each order carries a judgment label the agent chooses (for example ``scale_in`` or
``secure_then_add``), stored beside the request." The label sits beside the request with
the reason and tolerance: in the journal's annotation and on the Trade Approval row,
never in the request, its fingerprint or its operation id, so two sends that differ only
in label are one operation. The closed-trade row copies its opening order's label. The
PostgreSQL cases use the real migrated schema and the simulation broker.
"""

from decimal import Decimal
from typing import Any

import pytest
from lonora_contracts.trading import (
    AnnotatedTradeRequest,
    TradeAnnotation,
    judgment_label,
)
from pydantic import ValidationError
from test_closed_trades import ledger, quote, record
from test_proactive_wakes import call, database, retire, simulation
from test_trade_approval_validity import same_call

ENTRY = {"action": "buy", "symbol": "XAUUSD", "volume": "0.1", "stop_loss": "95"}


def test_a_label_is_an_agent_chosen_slug() -> None:
    assert TradeAnnotation(label="secure_then_add").label == "secure_then_add"
    assert TradeAnnotation().label == ""  # No label.
    for bad in ("Scale In", "scale-in", "x" * 41, "تعزيز"):
        with pytest.raises(ValidationError):
            TradeAnnotation(label=bad)
    # The tool never refuses an order over its label: it keeps the slug of what was sent.
    assert judgment_label("Take Profit") == "take_profit"
    assert judgment_label(" scale-in #2 ") == "scale_in_2"
    assert judgment_label("تعزيز") == ""
    assert len(judgment_label("x" * 200)) == 40
    request = AnnotatedTradeRequest.model_validate(
        {**ENTRY, "account_id": "acc", "label": "Take Profit"}
    )
    assert request.label == "Take Profit"


@pytest.mark.asyncio
async def test_two_sends_that_differ_only_in_label_are_one_operation() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import TradingJournalRow
    from lonora_db.trading_mode import set_trading_mode

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        await quote(fixture, connection, "100", "101")
        agent = await fixture.agent("Labelled", supervised=True)
        async with fixture.runtime.db.sessions() as session, session.begin():
            await set_trading_mode(session, fixture.owner, agent["id"], "full", by="owner_tap")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        entry = {**ENTRY, "account_id": connection}
        first = await call(context, "trade_execute", **entry, reason="Break", label="scale_in")
        assert first["status"] == "confirmed", first
        again = await call(
            context, "trade_execute", **entry, reason="Break", label="secure_then_add"
        )
        assert again["operation_id"] == first["operation_id"] and again["status"] == "confirmed"
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(TradingJournalRow, first["operation_id"])
            assert row is not None
            assert row.annotation == {"reason": "Break", "tolerance": None, "label": "scale_in"}
            assert "label" not in row.request
        # The position closes under a management label; its ledger row keeps the
        # opening order's label.
        closed = await call(
            context,
            "trade_execute",
            action="close_position",
            symbol="XAUUSD",
            position_id=first["broker_id"],
            account_id=connection,
            reason="Target",
            label="Partial Profit",
        )
        assert closed["status"] == "confirmed", closed
        async with fixture.runtime.db.sessions() as session:
            close_row = await session.get(TradingJournalRow, closed["operation_id"])
            assert close_row is not None and close_row.annotation is not None
            assert close_row.annotation["label"] == "partial_profit"
        assert await record(fixture, connection) == 1
        (trade,) = await ledger(fixture, connection)
        assert trade.label == "scale_in" and trade.opening_operation_id == first["operation_id"]
        assert trade.agent_id == agent["id"] and Decimal(trade.realized_pnl) == Decimal(-10)
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_card_keeps_the_label_and_the_approved_send_journals_it() -> None:
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow, TradeApprovalRow, TradingJournalRow

    fixture = await Fixture().open()
    connection = ""
    try:
        connection = await simulation(fixture, [])
        agent = await fixture.agent("Asks with a label", supervised=True)
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        arguments: dict[str, Any] = {
            **ENTRY,
            "account_id": connection,
            "reason": "Retest",
            "tolerance": "5",
            "label": "first_entry",
        }
        asked = await same_call(context, "labelled-card", **arguments)
        assert asked.get("approval_id"), asked
        async with fixture.runtime.db.sessions() as session, session.begin():
            card = await session.get(TradeApprovalRow, asked["approval_id"])
            assert card is not None and card.label == "first_entry"
            assert all("label" not in request for request in card.requests)
            waiting = await session.get(RunRow, context.lease.run_id, with_for_update=True)
            assert waiting is not None
            waiting.status = "waiting_input"
        tapped = await fixture.client.post(
            f"/api/trading/approvals/{asked['approval_id']}/decision",
            json={"decision": "approve"},
        )
        assert tapped.status_code == 200, tapped.text
        async with fixture.runtime.db.sessions() as session, session.begin():
            resumed = await session.get(RunRow, context.lease.run_id, with_for_update=True)
            assert resumed is not None
            resumed.status = "running"
        sent = await same_call(context, "labelled-card", **arguments)
        assert sent["status"] == "confirmed", sent
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(TradingJournalRow, sent["operation_id"])
            assert row is not None and row.annotation is not None
            assert row.annotation["label"] == "first_entry"
    finally:
        await retire(fixture, connection)
        await fixture.close()
