"""Integrity is measured from actual source data, with explicit consumer policies."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from lonora_contracts.account import AccountState
from lonora_contracts.market import Candle, Quote
from lonora_core.user_error import LonoraError
from lonora_market.health import (
    assess_account,
    assess_candles,
    assess_quote,
    require_healthy,
    timeframe_age_seconds,
)

NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


def quote(symbol: str = "EURUSDm", seconds: int = 0) -> Quote:
    return Quote(
        symbol=symbol,
        bid=Decimal("1.1"),
        ask=Decimal("1.2"),
        observed_at=NOW - timedelta(seconds=seconds),
        source="scripted-broker",
    )


def bars(symbol: str, timeframe: str, offsets: list[int]) -> list[Candle]:
    return [
        Candle(
            symbol=symbol,
            timeframe=timeframe,
            time=NOW - timedelta(seconds=value),
            open=Decimal(10),
            high=Decimal(12),
            low=Decimal(9),
            close=Decimal(11),
        )
        for value in offsets
    ]


@pytest.mark.parametrize("symbol", ["EURUSDm", "XAUUSDm", "US500.cash", "BTCUSD.r"])
def test_quote_source_freshness_exact_identity_and_receive_age(symbol: str) -> None:
    health = assess_quote(
        quote(symbol, 300),
        account_id="a",
        symbol=symbol,
        now=NOW,
        maximum_age_seconds=30,
        received_at=NOW,
    )
    assert health.state == "stale" and health.reason_code == "market_quote_stale"
    assert health.symbol == symbol
    with pytest.raises(LonoraError, match="market_quote_stale"):
        require_healthy(health)
    health = assess_quote(
        quote(symbol),
        account_id="a",
        symbol=symbol,
        now=NOW,
        maximum_age_seconds=30,
        received_at=NOW - timedelta(seconds=300),
        maximum_receive_age_seconds=30,
    )
    assert health.reason_code == "market_quote_receive_stale"
    assert assess_quote(
        quote(symbol), account_id="a", symbol=symbol, now=NOW, maximum_age_seconds=30
    ).healthy


def test_quote_unknown_invalid_and_wrong_symbol_are_not_live() -> None:
    args = dict(account_id="a", symbol="EURUSDm", now=NOW, maximum_age_seconds=30)
    assert assess_quote(None, **args).state == "unavailable"
    assert assess_quote(quote("EURUSD"), **args).reason_code == "broker_symbol_mismatch"
    impossible = quote().model_copy(update={"ask": Decimal("NaN")})
    assert assess_quote(impossible, **args).reason_code == "market_quote_invalid"
    future = quote().model_copy(update={"observed_at": NOW + timedelta(minutes=1)})
    assert assess_quote(future, **args).reason_code == "market_quote_timestamp_future"


@pytest.mark.parametrize(
    "symbol,timeframe,step",
    [
        ("EURUSDm", "1m", 60),
        ("XAUUSDm", "15m", 900),
        ("US500.cash", "4h", 14400),
        ("BTCUSD.r", "1d", 86400),
    ],
)
def test_candle_integrity_uses_explicit_cadence(symbol: str, timeframe: str, step: int) -> None:
    args = dict(
        account_id="a",
        symbol=symbol,
        timeframe=timeframe,
        now=NOW,
        maximum_age_seconds=timeframe_age_seconds(timeframe),
    )
    healthy = assess_candles(
        bars(symbol, timeframe, [step * 2, step, 0]), expected_interval_seconds=step, **args
    )
    assert healthy.healthy and healthy.symbol == symbol
    missing = assess_candles(
        bars(symbol, timeframe, [step * 3, step, 0]), expected_interval_seconds=step, **args
    )
    assert missing.reason_code == "market_candle_gap"
    # Without a known market calendar, a weekend/session gap is not declared missing.
    unknown = assess_candles(bars(symbol, timeframe, [step * 3, step, 0]), **args)
    assert unknown.healthy and unknown.measurements["continuity"] == "unknown"
    assert (
        assess_candles(bars(symbol, timeframe, [step, step, 0]), **args).reason_code
        == "duplicate_candle_timestamp"
    )
    assert (
        assess_candles(bars(symbol, timeframe, [0, step]), **args).reason_code
        == "market_candle_out_of_order"
    )
    assert assess_candles(bars(symbol, timeframe, [step * 10]), **args).state == "stale"


def test_account_freshness_and_last_good_are_explicit() -> None:
    account = AccountState(
        id="broker-id",
        currency="USD",
        balance=Decimal(1000),
        equity=Decimal(1000),
        margin=Decimal(0),
        free_margin=Decimal(1000),
        observed_at=NOW - timedelta(minutes=5),
    )
    previous = NOW - timedelta(minutes=6)
    health = assess_account(
        account,
        account_id="local-connection",
        now=NOW,
        maximum_age_seconds=30,
        last_good_at=previous,
    )
    assert health.state == "stale" and health.last_good_at == previous
    assert health.account_id == "local-connection"


def test_all_canonical_timeframes_have_explicit_freshness_horizon() -> None:
    from lonora_core.chart_controller import TIMEFRAMES

    assert all(timeframe_age_seconds(timeframe) > 0 for timeframe in TIMEFRAMES)
    assert timeframe_age_seconds("1mn") == 62 * 86400
