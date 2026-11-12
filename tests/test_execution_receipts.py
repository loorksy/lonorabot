"""What an Execution Receipt shows, read from the confirmed journal row (mandate 10.3).

Fills: ticket, action, volume, fill price as the broker reported them. Placed orders:
ticket and the accepted order. Modifications: ticket and new values. Cancels: ticket.
The agent's reason comes from beside the request; the owner's own order has none.
"""

from typing import Any

from lonora_contracts.domain import utcnow
from lonora_db.execution_receipts import receipt_data, receipt_facts
from lonora_db.schema import ExecutionReceiptRow, TradingJournalRow


def journal(request: dict[str, Any], details: dict[str, Any], **result: Any) -> TradingJournalRow:
    return TradingJournalRow(
        operation_id="op",
        owner_id="owner",
        account_id="account",
        request={"account_id": "account", "operation_id": "op", "symbol": "XAUUSD", **request},
        status="confirmed",
        result={"operation_id": "op", "status": "confirmed", "details": details, **result},
        annotation={"reason": "Breakout above 2,400", "tolerance": "1.5"},
        updated_at=utcnow(),
    )


def test_a_fill_shows_the_brokers_ticket_volume_and_price() -> None:
    row = journal(
        {"action": "buy", "volume": "0.3"},
        {"position_id": 50071, "volume": 0.3, "price": 2400.55, "order_id": 50070},
        broker_id="50070",
    )
    assert receipt_facts(row) == {
        "kind": "fill",
        "action": "buy",
        "symbol": "XAUUSD",
        "ticket": "50071",
        "volume": "0.3",
        "price": "2400.55",
        "partial": False,
    }


def test_a_partial_fill_never_claims_the_requested_volume() -> None:
    row = journal({"action": "sell", "volume": "1"}, {"partial_execution": True}, broker_id="9")
    facts = receipt_facts(row)
    assert facts["partial"] is True and facts["volume"] is None and facts["price"] is None
    # Nothing the broker did not report: no volume is inferred from the request.
    full = receipt_facts(journal({"action": "sell", "volume": "1"}, {}, broker_id="9"))
    assert full["volume"] is None and full["ticket"] == "9"


def test_changes_to_an_existing_ticket_name_that_ticket() -> None:
    close = receipt_facts(
        journal({"action": "close_position", "position_id": "77", "volume": "0.1"}, {})
    )
    assert close["kind"] == "fill" and close["ticket"] == "77"
    modify = receipt_facts(
        journal(
            {
                "action": "modify_position",
                "position_id": "77",
                "stop_loss": "2400",
                "clear_take_profit": True,
            },
            {},
            broker_id="other",
        )
    )
    assert modify == {
        "kind": "modify",
        "action": "modify_position",
        "symbol": "XAUUSD",
        "ticket": "77",
        "price": None,
        "stop_loss": "2400",
        "take_profit": None,
        "stop_loss_removed": False,
        "take_profit_removed": True,
    }
    cancel = receipt_facts(journal({"action": "cancel_order", "order_id": "88"}, {}))
    assert cancel == {
        "kind": "cancel",
        "action": "cancel_order",
        "symbol": "XAUUSD",
        "ticket": "88",
    }


def test_a_placed_order_shows_the_order_the_broker_accepted() -> None:
    facts = receipt_facts(
        journal(
            {"action": "buy_limit", "volume": "0.2", "price": "2390", "stop_loss": "2380"},
            {"order_id": 60001},
            broker_id="60001",
        )
    )
    assert facts["kind"] == "order" and facts["ticket"] == "60001"
    assert (facts["volume"], facts["price"], facts["stop_loss"]) == ("0.2", "2390", "2380")


def test_the_reason_is_the_agents_and_the_owners_order_has_none() -> None:
    row = journal({"action": "buy", "volume": "0.1"}, {"verification": {"status": "pending"}})
    agent = ExecutionReceiptRow(operation_id="op", owner_id="owner", agent_id="agent")
    agent.created_at = utcnow()
    data = receipt_data(agent, row)
    assert data["reason"] == "Breakout above 2,400" and data["verification"] == "pending"
    owner = ExecutionReceiptRow(operation_id="op", owner_id="owner", agent_id=None)
    owner.created_at = utcnow()
    assert receipt_data(owner, row)["reason"] is None


def test_a_fill_reconciled_from_a_tickets_current_state_shows_no_volume_or_price() -> None:
    # A 1.00 buy, reconciled later from its open position, which now holds 0.40.
    row = journal(
        {"action": "buy", "volume": "1"},
        {"reconciled": True, "position_id": "p1", "deal_id": None, "volume": 0.4, "price": 2400},
        broker_id="p1",
    )
    facts = receipt_facts(row)
    assert facts["ticket"] == "p1" and facts["volume"] is None and facts["price"] is None
    # Reconciled from the fill's own deal: the deal's numbers are the fill's.
    deal = journal(
        {"action": "buy", "volume": "1"},
        {"reconciled": True, "position_id": "p1", "deal_id": "d1", "volume": 1.0, "price": 2401},
        broker_id="d1",
    )
    assert (receipt_facts(deal)["volume"], receipt_facts(deal)["price"]) == ("1.0", "2401")
