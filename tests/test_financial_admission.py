"""Pure rules for scoped financial admission and evidence-based recovery (no broker, no DB)."""

from datetime import timedelta
from decimal import Decimal
from typing import Any

import pytest
from lonora_contracts.account import Order, Position
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import (
    TERMINAL_STATUSES,
    UNRESOLVED_STATUSES,
    OperationResolution,
    TradeRequest,
    TradeResult,
    TradingControl,
)
from lonora_core.trading_control import require_trading
from lonora_core.user_error import LonoraError
from lonora_db.schema import TradingJournalRow
from lonora_tools.trade import halted_receipts
from lonora_trading.admission import may_reduce_risk, risk_reducing
from lonora_trading.operation_events import awaiting_broker_confirmation, send_state
from lonora_trading.target_state import SETTLE_WINDOW, target_state_receipt
from pydantic import ValidationError


def position(side: str = "buy", **fields: Any) -> Position:
    return Position.model_validate(
        {
            "id": "p1",
            "symbol": "XAUUSD",
            "side": side,
            "volume": Decimal("1"),
            "open_price": Decimal(2000),
            "stop_loss": Decimal(1990) if side == "buy" else Decimal(2010),
            "take_profit": Decimal(2020) if side == "buy" else Decimal(1980),
            **fields,
        }
    )


def order(**fields: Any) -> Order:
    return Order.model_validate(
        {
            "id": "o1",
            "symbol": "XAUUSD",
            "side": "buy_limit",
            "volume": Decimal("0.5"),
            "price": Decimal(1995),
            **fields,
        }
    )


def request(action: str, **fields: Any) -> TradeRequest:
    return TradeRequest.model_validate(
        {"account_id": "acct", "operation_id": "op", "action": action, "symbol": "XAUUSD", **fields}
    )


@pytest.mark.parametrize(
    ("trade", "target", "expected"),
    [
        (request("close_position", position_id="p1"), position(), True),
        (request("close_position", position_id="p1", volume="0.4"), position(), True),
        (request("close_position", position_id="p1", volume="1"), position(), True),
        (request("close_position", position_id="p1", volume="1.5"), position(), False),
        (request("close_position", position_id="p1"), None, False),
        (request("close_position", position_id="p1"), position(symbol="EURUSD"), False),
        (request("close_position", position_id="p1"), position(id="p2"), False),
        (request("cancel_order", order_id="o1"), order(), True),
        (request("cancel_order", order_id="o1"), None, False),
        (request("cancel_order", order_id="o1"), order(symbol="EURUSD"), False),
        # Stop-loss strictly toward the market: up for a buy, down for a sell.
        (request("modify_position", position_id="p1", stop_loss="1995"), position(), True),
        (request("modify_position", position_id="p1", stop_loss="1990"), position(), False),
        (request("modify_position", position_id="p1", stop_loss="1985"), position(), False),
        (request("modify_position", position_id="p1", stop_loss="2005"), position("sell"), True),
        (request("modify_position", position_id="p1", stop_loss="2015"), position("sell"), False),
        (
            request("modify_position", position_id="p1", stop_loss="1999"),
            position(stop_loss=None),
            True,
        ),
        (
            request("modify_position", position_id="p1", stop_loss="1995", take_profit="2020"),
            position(),
            True,
        ),
        (
            request("modify_position", position_id="p1", stop_loss="1995", take_profit="2030"),
            position(),
            False,
        ),
        (
            request("modify_position", position_id="p1", stop_loss="1995", clear_take_profit=True),
            position(),
            False,
        ),
        (request("modify_position", position_id="p1", clear_stop_loss=True), position(), False),
        (request("modify_position", position_id="p1", take_profit="2010"), position(), False),
        (request("modify_position", position_id="p1", stop_loss="1995"), position("hedge"), False),
        (request("modify_order", order_id="o1", stop_loss="1994"), order(), False),
        (request("buy", volume="0.1"), None, False),
        (request("sell_limit", volume="0.1", price="2050"), None, False),
    ],
)
def test_risk_reducing_is_judged_against_the_current_broker_target(
    trade: TradeRequest, target: Position | Order | None, expected: bool
) -> None:
    assert risk_reducing(trade, target) is expected
    if expected:
        assert may_reduce_risk(trade)


def test_global_controls_stop_new_risk_but_never_trap_an_exit() -> None:
    for controls, code in (
        (TradingControl(enabled=True, emergency_stop=True), "emergency_stop"),
        (TradingControl(enabled=False), "trading_disabled"),
    ):
        with pytest.raises(LonoraError) as error:
            require_trading(controls)
        assert error.value.code == code
        require_trading(controls, risk_reducing=True)
    require_trading(TradingControl(enabled=True))


def test_status_sets_partition_the_lifecycle() -> None:
    assert UNRESOLVED_STATUSES == {"submitted", "ambiguous"}
    assert TERMINAL_STATUSES == {"confirmed", "failed", "resolved"}
    assert not UNRESOLVED_STATUSES & TERMINAL_STATUSES
    assert "reserved" not in UNRESOLVED_STATUSES | TERMINAL_STATUSES


def receipt(trade: TradeRequest, positions: list[Position], orders: list[Order], **kw: Any):
    now = utcnow()
    return target_state_receipt(
        "op",
        trade,
        positions,
        orders,
        submitted_at=kw.pop("submitted_at", now - SETTLE_WINDOW - timedelta(seconds=1)),
        observed_at=now,
        **kw,
    )


def test_modify_reconciles_by_comparing_requested_fields_with_the_target() -> None:
    trade = request("modify_position", position_id="p1", stop_loss="1995")
    matched = receipt(trade, [position(stop_loss=Decimal("1995.00"))], [])
    assert matched and matched.status == "confirmed" and matched.code == "target_state_matches"
    assert matched.details["evidence"] == "broker_target_state"
    missed = receipt(trade, [position()], [])
    assert missed and missed.status == "failed" and missed.code == "target_state_not_reached"
    # Inside the settle window a lost request may still apply: keep the uncertainty.
    assert receipt(trade, [position()], [], submitted_at=utcnow()) is None
    cleared = request("modify_position", position_id="p1", clear_stop_loss=True)
    cleared_receipt = receipt(cleared, [position(stop_loss=Decimal(0))], [])
    assert cleared_receipt and cleared_receipt.status == "confirmed"
    gone = receipt(trade, [], [])
    assert gone and gone.status == "resolved" and gone.code == "target_closed"
    assert gone.details["resolution"] == {"source": "broker_state", "basis": "target_closed"}
    priced = request("modify_order", order_id="o1", price="1990", take_profit="2010")
    hit = receipt(priced, [], [order(price=Decimal(1990), take_profit=Decimal(2010))])
    assert hit and hit.status == "confirmed"
    partial = receipt(priced, [], [order(price=Decimal(1990))])
    assert partial and partial.status == "failed"
    vanished = receipt(priced, [], [])
    assert (
        vanished and vanished.status == "resolved" and vanished.code == "target_no_longer_pending"
    )


def test_cancel_reconciles_from_order_absence_and_fill_history() -> None:
    trade = request("cancel_order", order_id="o1")
    cancelled = receipt(trade, [], [], deals=[])
    assert cancelled and cancelled.status == "confirmed"
    assert cancelled.code == "order_no_longer_pending"
    pending = receipt(trade, [], [order()], deals=[])
    assert pending and pending.status == "failed" and pending.code == "target_state_not_reached"
    # Without fill history an absent order might have become a position.
    assert receipt(trade, [], [], deals=None) is None
    assert receipt(trade, [], [], deals=[], submitted_at=utcnow()) is None
    fill = [{"orderId": "o1", "volume": 0.5}]
    filled = receipt(trade, [], [], deals=fill, before=order())
    assert filled and filled.status == "failed" and filled.code == "order_filled_before_cancel"
    partly = [{"orderId": "o1", "volume": 0.2}]
    assert receipt(trade, [], [], deals=partly, before=order()) is None
    opened = position(id="o1")
    assert receipt(trade, [opened], [], deals=[], before=order()) is None


def test_close_reconciles_only_where_target_state_is_conclusive() -> None:
    full = request("close_position", position_id="p1")
    closed = receipt(full, [], [])
    assert closed and closed.status == "confirmed" and closed.code == "position_no_longer_open"
    still_open = receipt(full, [position()], [])
    assert still_open and still_open.status == "failed"
    assert receipt(full, [position()], [], submitted_at=utcnow()) is None
    partial = request("close_position", position_id="p1", volume="0.5")
    assert receipt(partial, [position(volume=Decimal("0.5"))], []) is None
    moot = receipt(partial, [], [])
    assert moot and moot.status == "resolved"
    # Incremental creates are never inferred from account state.
    assert receipt(request("buy", volume="0.1"), [position()], []) is None


def journal(status: str, details: dict[str, Any]) -> TradingJournalRow:
    return TradingJournalRow(
        operation_id="op",
        owner_id="owner",
        account_id="acct",
        request_hash="hash",
        request={"symbol": "XAUUSD", "action": "buy"},
        status=status,
        result={"operation_id": "op", "status": status, "details": details},
        updated_at=utcnow(),
    )


def test_send_state_comes_from_the_persisted_boundary_not_a_broker_reply() -> None:
    assert send_state(journal("reserved", {"execution": {}})) == "not_sent"
    assert send_state(journal("submitted", {"execution": {"send_authorized": True}})) == "sent"
    assert send_state(journal("failed", {"send_state": "not_sent", "execution": {}})) == "not_sent"
    assert send_state(journal("failed", {"execution": {"send_authorized": True}})) == "sent"
    assert send_state(journal("failed", {"execution": {"run_id": None}})) == "not_sent"
    assert send_state(journal("ambiguous", {})) == "unknown"
    pending = journal("confirmed", {"verification": {"status": "pending"}})
    assert awaiting_broker_confirmation(pending)
    assert not awaiting_broker_confirmation(
        journal("confirmed", {"verification": {"status": "verified"}})
    )
    assert awaiting_broker_confirmation(journal("ambiguous", {}))
    assert not awaiting_broker_confirmation(journal("resolved", {}))


def test_halted_batch_reports_remaining_operations_as_never_sent() -> None:
    remaining = [
        request("close_position", operation_id="op-2", position_id="p2"),
        request("close_position", operation_id="op-3", position_id="p3"),
    ]
    after = TradeResult(operation_id="op-1", status="ambiguous")
    halted = halted_receipts(remaining, after)
    assert [item["operation_id"] for item in halted] == ["op-2", "op-3"]
    assert {item["status"] for item in halted} == {"failed"}
    assert all(
        item["details"] == {"send_state": "not_sent", "halted_after": "op-1"} for item in halted
    )


def test_owner_resolution_requires_a_substantive_statement() -> None:
    resolution = OperationResolution(
        outcome="not_executed", statement="  Checked MT5: no order  ", broker_reference=" "
    )
    assert resolution.statement == "Checked MT5: no order" and resolution.broker_reference is None
    with pytest.raises(ValidationError):
        OperationResolution(outcome="executed", statement="   ")
    with pytest.raises(ValidationError):
        OperationResolution.model_validate({"outcome": "confirmed", "statement": "x"})
