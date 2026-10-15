"""Measured execution and portfolio facts, using explicit broker fixtures only."""

from datetime import timedelta
from decimal import Decimal

import pytest
from lonora_contracts.account import AccountState, Order, Position
from lonora_contracts.domain import utcnow
from lonora_contracts.execution_quality import ExecutionPolicy, ExecutionSnapshot
from lonora_contracts.market import Quote
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_trading.execution_quality import actual_execution, evaluate_execution
from lonora_trading.exposure import account_exposure


def snapshot() -> ExecutionSnapshot:
    now = utcnow()
    return ExecutionSnapshot(
        account=AccountState(
            id="account",
            currency="USD",
            balance=Decimal("10000"),
            equity=Decimal("10000"),
            margin=Decimal("0"),
            free_margin=Decimal("10000"),
            observed_at=now,
        ),
        positions=[],
        orders=[],
        observed_at=now,
        quote=Quote(
            symbol="EURUSDm",
            bid=Decimal("1.1"),
            ask=Decimal("1.1002"),
            observed_at=now,
            source="fixture",
        ),
    )


def request(action: str = "buy") -> TradeRequest:
    return TradeRequest.model_validate(
        dict(account_id="account", symbol="EURUSDm", action=action, volume=Decimal("0.1"))
    )


def test_fresh_and_unknown_liquidity() -> None:
    result = evaluate_execution(request(), snapshot(), ExecutionPolicy())
    assert result.state == "executable"
    assert result.liquidity == "unknown" and result.spread_reference is None
    assert result.exposure.notional is None and result.exposure.monetary_stop_risk is None


@pytest.mark.parametrize("resource", ["quote", "account"])
def test_stale_source_not_refreshed_by_snapshot_read(resource: str) -> None:
    state = snapshot()
    source = state.quote if resource == "quote" else state.account
    assert source is not None
    source.observed_at -= timedelta(minutes=3)
    quality = evaluate_execution(request(), state, ExecutionPolicy())
    assert quality.state == "blocked"
    assert any("stale" in reason for reason in quality.reasons)


def test_spread_server_limit_and_exact_suffix() -> None:
    state = snapshot()
    assert (
        evaluate_execution(request(), state, ExecutionPolicy(max_spread=Decimal("0.0001"))).state
        == "blocked"
    )
    assert state.quote is not None
    state.quote.symbol = "EURUSD"
    assert (
        "broker_symbol_mismatch" in evaluate_execution(request(), state, ExecutionPolicy()).reasons
    )


def test_cross_agent_manual_and_pending_exposure_no_symbol_rewrite() -> None:
    state = snapshot()
    state.positions = [
        Position(
            id="manual",
            symbol="EURUSDm",
            side="buy",
            volume=Decimal("0.2"),
            open_price=Decimal("1.1"),
        ),
        Position(
            id="agent-other",
            symbol="EURUSDm",
            side="sell",
            volume=Decimal("0.3"),
            open_price=Decimal("1.1"),
            stop_loss=Decimal("1.2"),
        ),
        Position(
            id="metal",
            symbol="XAUUSDm",
            side="buy",
            volume=Decimal("0.1"),
            open_price=Decimal("2600"),
        ),
    ]
    state.orders = [
        Order(
            id="pending",
            symbol="EURUSDm",
            side="buy_limit",
            volume=Decimal("0.2"),
            price=Decimal("1.0"),
        )
    ]
    exposure = account_exposure(state)
    long = next(
        item for item in exposure.buckets if item.symbol == "EURUSDm" and item.direction == "buy"
    )
    assert long.position_volume == Decimal("0.2") and long.pending_volume == Decimal("0.2")
    assert long.unprotected_positions == 1
    policy = ExecutionPolicy(max_symbol_direction_volume=Decimal("0.4"))
    assert (
        "portfolio_direction_volume_limit" in evaluate_execution(request(), state, policy).reasons
    )
    assert evaluate_execution(request("sell"), state, policy).state == "executable"


@pytest.mark.parametrize(
    "side,fill,expected",
    [("buy", "1.1003", "0.0001"), ("sell", "1.0999", "0.0001"), ("sell", "1.1001", "-0.0001")],
)
def test_directional_slippage_only_actual_broker_fields(
    side: str, fill: str, expected: str
) -> None:
    trade = request(side)
    quality = evaluate_execution(trade, snapshot(), ExecutionPolicy())
    result = TradeResult(
        operation_id=trade.operation_id, status="confirmed", details={"price": fill}
    )
    measured = actual_execution(trade, result, quality)
    assert Decimal(measured["adverse_slippage"]) == Decimal(expected)
    assert measured["slippage_unit"] == "price"
    assert "broker_reported_volume" not in measured


def test_ambiguous_receipt_never_invents_fill() -> None:
    trade = request()
    measured = actual_execution(
        trade,
        TradeResult(operation_id=trade.operation_id, status="ambiguous", details={"price": "1.1"}),
        None,
    )
    assert "actual_fill_price" not in measured


def test_risk_reduction_allowed_above_entry_cap() -> None:
    state = snapshot()
    trade = TradeRequest(
        account_id="account", action="close_position", symbol="EURUSDm", position_id="manual"
    )
    assert evaluate_execution(trade, state, ExecutionPolicy(max_positions=0)).state == "executable"


def test_drift_uses_actual_stop_distance_and_server_policy() -> None:
    trade = request()
    trade.stop_loss = Decimal("1.09")
    initial = snapshot()
    current = snapshot()
    assert initial.quote is not None and current.quote is not None
    current.quote.ask = Decimal("1.104")
    policy = ExecutionPolicy(max_entry_drift_stop_fraction=Decimal("0.1"))
    quality = evaluate_execution(trade, current, policy, planned_quote=initial.quote)
    assert quality.state == "blocked"
    assert "execution_entry_deteriorated" in quality.reasons
    assert quality.drift_tolerance == Decimal("0.00102")


def test_drift_never_invents_stop_reference() -> None:
    trade = request()
    state = snapshot()
    quality = evaluate_execution(
        trade,
        state,
        ExecutionPolicy(max_entry_drift_stop_fraction=Decimal("0.1")),
        planned_quote=state.quote,
    )
    assert "execution_drift_reference_unavailable" in quality.reasons
