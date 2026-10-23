"""Strict market structure uses synthetic OHLC, no provider or financial effects."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from lonora_contracts.market import Candle
from lonora_contracts.market_intelligence import Observation, TrendlineAnchor
from lonora_core.chart_annotations import validate_annotations
from lonora_core.chart_controller import TIMEFRAMES
from lonora_core.user_error import LonoraError
from lonora_market.structure import analyze_structure
from lonora_market.watch_lifecycle import candle_close_time

START = datetime(2024, 1, 1, tzinfo=UTC)


def bars(values: list[int], *, symbol: str = "XAUUSDm", timeframe: str = "1m") -> list[Candle]:
    result: list[Candle] = []
    opened = START
    for value in values:
        result.append(
            Candle(
                symbol=symbol,
                timeframe=timeframe,
                time=opened,
                open=Decimal(value),
                high=Decimal(value + 1),
                low=Decimal(value - 1),
                close=Decimal(value),
            )
        )
        opened = candle_close_time(opened, timeframe)
    return result


def analyze(data: list[Candle], **kwargs: Any) -> dict[str, Any]:
    return analyze_structure(
        data,
        account_id="account",
        symbol=data[0].symbol if data else "XAUUSDm",
        timeframe=data[0].timeframe if data else "1m",
        observed_at=kwargs.pop(
            "observed_at", candle_close_time(data[-1].time, data[-1].timeframe) if data else START
        ),
        left_bars=kwargs.pop("left_bars", 1),
        right_bars=kwargs.pop("right_bars", 1),
        **kwargs,
    )


@pytest.mark.parametrize("symbol", ["EURUSDm", "XAUUSD.raw", "US500.cash", "BTCUSD.r"])
@pytest.mark.parametrize("timeframe", sorted(TIMEFRAMES))
def test_exact_symbol_every_timeframe_and_shared_observation_contract(
    symbol: str, timeframe: str
) -> None:
    data = bars([10, 14, 10, 15, 11, 16, 12], symbol=symbol, timeframe=timeframe)
    result = analyze(data)
    assert result["symbol"] == symbol and result["timeframe"] == timeframe
    assert result["health"]["state"] == "healthy"
    assert result["health"]["measurements"]["continuity"] == "unknown"
    assert result["execution_authorized"] is False
    assert result["pivots"] and result["trendlines"]
    for payload in result["pivots"] + result["trendlines"]:
        fact = Observation.model_validate(payload)
        assert fact.symbol == symbol and fact.timeframe == timeframe
        assert fact.detector_version == "1" and fact.values["execution_authorized"] is False
        assert fact.values["source_hash"] and fact.values["methodology"] == result["methodology"]
    assert json.loads(json.dumps(result)) == result


def test_confirmation_waits_until_last_right_bar_closes() -> None:
    data = bars([10, 14, 10])
    developing = analyze(data, observed_at=data[-1].time + timedelta(seconds=59))
    assert developing["pivots"] == []
    assert developing["input"]["excluded_forming_bars"] == 1
    confirmed = analyze(data)
    high = confirmed["pivots"][0]
    assert high["values"]["kind"] == "swing_high"
    assert high["values"]["time"] == data[1].time.isoformat()
    assert high["values"]["available_at"] == candle_close_time(data[-1].time, "1m").isoformat()
    assert datetime.fromisoformat(high["observed_at"].replace("Z", "+00:00")) == candle_close_time(
        data[-1].time, "1m"
    )


def test_asymmetric_swing_windows_and_low_confirmation_are_explicit() -> None:
    data = bars([14, 12, 8, 11, 13])
    assert analyze(data, left_bars=2, right_bars=2, observed_at=data[-1].time)["pivots"] == []
    facts = analyze(data, left_bars=2, right_bars=2)["pivots"]
    assert len(facts) == 1 and facts[0]["values"]["kind"] == "swing_low"
    assert facts[0]["values"]["price"] == "7"
    assert facts[0]["values"]["available_at"] == candle_close_time(data[-1].time, "1m").isoformat()
    assert analyze(data, left_bars=1, right_bars=3)["configuration"]["right_bars"] == 3


def test_causal_prefix_replay_does_not_rewrite_confirmed_facts() -> None:
    data = bars([10, 14, 10, 15, 11, 16, 12, 17, 13])
    full = analyze(data, max_pivots=100)
    for length in range(1, len(data) + 1):
        prefix = analyze(data[:length], max_pivots=100)
        now = candle_close_time(data[length - 1].time, "1m")
        expected = [
            fact
            for fact in full["pivots"]
            if datetime.fromisoformat(fact["values"]["available_at"]) <= now
        ]
        assert prefix["pivots"] == expected
        assert prefix == analyze(data[:length], max_pivots=100)


def test_live_ohlc_cannot_supply_confirmation_or_change_source_hash() -> None:
    data = bars([10, 14, 10, 15, 11, 16, 12])
    now = data[-1].time + timedelta(seconds=30)
    first = analyze(data, observed_at=now)
    modified = data[:-1] + [
        data[-1].model_copy(update={"high": Decimal(999), "low": Decimal(1), "close": Decimal(900)})
    ]
    changed = analyze(modified, observed_at=now)
    assert changed["source_hash"] == first["source_hash"]
    assert changed["pivots"] == first["pivots"]
    assert changed["trendlines"] == first["trendlines"]


def test_corrected_closed_ohlc_changes_source_and_relevant_pivot_identity() -> None:
    data = bars([10, 14, 10, 15, 11])
    first = analyze(data)
    changed = analyze([data[0], data[1].model_copy(update={"high": Decimal(16)}), *data[2:]])
    assert changed["source_hash"] != first["source_hash"]
    assert changed["pivots"][0]["id"] != first["pivots"][0]["id"]
    assert changed["pivots"][0]["values"]["price"] == "16"


@pytest.mark.parametrize("values", [[10, 14, 14, 10], [10, 10, 10, 10], [10, 11, 12, 13]])
def test_ties_flat_and_monotonic_bars_do_not_invent_extrema(values: list[int]) -> None:
    assert analyze(bars(values))["pivots"] == []


def test_original_decimal_prices_survive_without_float_conversion() -> None:
    data = bars([10, 14, 10])
    price = Decimal("14.123456789012345678901234567890123456789")
    data[1] = data[1].model_copy(update={"high": price})
    assert analyze(data)["pivots"][0]["values"]["price"] == str(price)


def test_multiple_recent_line_alternatives_use_existing_geometry() -> None:
    result = analyze(bars([10, 12, 10, 14, 11, 15, 12, 16, 13]), max_lines=6)
    lines = result["trendlines"]
    assert len(lines) == 6
    assert [line["values"]["role"] for line in lines] == ["support", "resistance"] * 3
    identities: set[tuple[str, str]] = set()
    for line in lines:
        values = line["values"]
        left, right = [TrendlineAnchor.model_validate(anchor) for anchor in values["anchors"]]
        assert left.time < right.time
        assert values["touch_count"] >= 2
        assert line["state"] == "confirmed"
        assert values["invalidation_reasons"] == []
        identities.add((values["anchor_observation_ids"][0], values["anchor_observation_ids"][1]))
        validate_annotations(
            [{"type": "trend_line", "start": values["anchors"][0], "end": values["anchors"][1]}]
        )
    assert len(identities) == 6


def test_closed_close_breaks_invalidate_and_explicit_tolerance_is_in_price_units() -> None:
    data = bars([10, 12, 10, 13, 11, 14, 12, 15, 10])
    first = analyze(data, tolerance=Decimal(0))
    support = next(line for line in first["trendlines"] if line["values"]["role"] == "support")
    assert support["state"] == "invalidated"
    assert support["values"]["first_break"]["close"] == "10"
    assert support["values"]["break_count"] == 1
    assert support["values"]["breaks"][0]["after_line_available"] is True
    held = analyze(data, tolerance=Decimal(2))
    same = next(
        line
        for line in held["trendlines"]
        if line["values"]["anchors"] == support["values"]["anchors"]
    )
    assert same["state"] == "confirmed" and same["values"]["break_count"] == 0


def test_wick_breach_without_closed_close_breach_does_not_invalidate_support() -> None:
    data = bars([10, 12, 10, 13, 11, 14, 12, 15, 13])
    data[-1] = data[-1].model_copy(update={"low": Decimal(1)})
    support = next(
        line for line in analyze(data)["trendlines"] if line["values"]["role"] == "support"
    )
    assert support["state"] == "confirmed" and support["values"]["break_count"] == 0


def test_resistance_close_breaks_and_bounded_break_evidence() -> None:
    data = bars([10, 12, 10, 13, 11, 14, 12, 15, 20])
    resistance = next(
        line for line in analyze(data)["trendlines"] if line["values"]["role"] == "resistance"
    )
    assert resistance["state"] == "invalidated"
    assert resistance["values"]["breaks"][-1]["close"] == "20"
    prolonged = bars([100, 104, 101, 105, 102, 106, *range(90, 50, -1)])
    support = next(
        line for line in analyze(prolonged)["trendlines"] if line["values"]["role"] == "support"
    )
    assert support["state"] == "invalidated"
    assert support["values"]["break_count"] > 12
    assert len(support["values"]["breaks"]) == 12 and support["values"]["breaks_truncated"]
    assert support["values"]["first_break"]["time"] < support["values"]["breaks"][0]["time"]


def test_unknown_broker_sessions_do_not_turn_gaps_into_claimed_continuity() -> None:
    data = bars([10, 14, 10, 15, 11])
    data[3:] = [bar.model_copy(update={"time": bar.time + timedelta(days=3)}) for bar in data[3:]]
    result = analyze(data)
    assert result["health"]["measurements"]["continuity"] == "unknown"
    assert any("session continuity" in limitation for limitation in result["limitations"])
    assert result["pivots"]


def test_window_and_result_bounds_are_explicit() -> None:
    data = bars([10, 14, 10, 15, 11, 16, 12, 17, 13])
    bounded = analyze(data, max_pivots=3, max_lines=1)
    assert len(bounded["pivots"]) == 3 and bounded["pivots_truncated"] is True
    assert len(bounded["trendlines"]) <= 1
    wide = analyze(data, left_bars=2, right_bars=2)
    assert wide["configuration"]["left_bars"] == wide["configuration"]["right_bars"] == 2
    assert analyze(data[:2])["pivots"] == []
    assert any("Insufficient closed bars" in value for value in analyze(data[:2])["limitations"])


@pytest.mark.parametrize(
    "kwargs,code",
    [
        ({"left_bars": 0}, "market_structure_windows_invalid"),
        ({"right_bars": 101}, "market_structure_windows_invalid"),
        ({"left_bars": True}, "market_structure_windows_invalid"),
        ({"right_bars": 1.5}, "market_structure_windows_invalid"),
        ({"max_pivots": 0}, "market_structure_counts_invalid"),
        ({"max_pivots": 101}, "market_structure_counts_invalid"),
        ({"max_lines": 25}, "market_structure_counts_invalid"),
        ({"max_lines": True}, "market_structure_counts_invalid"),
        ({"tolerance": Decimal(-1)}, "market_structure_tolerance_invalid"),
        ({"tolerance": Decimal("NaN")}, "market_structure_tolerance_invalid"),
        ({"tolerance": Decimal("Infinity")}, "market_structure_tolerance_invalid"),
        ({"tolerance": 1.0}, "market_structure_tolerance_invalid"),
        ({"observed_at": START.replace(tzinfo=None)}, "market_structure_timestamp_invalid"),
    ],
)
def test_invalid_configuration_has_useful_errors(kwargs: dict[str, Any], code: str) -> None:
    with pytest.raises(LonoraError, match=code):
        analyze(bars([10, 14, 10]), **kwargs)


@pytest.mark.parametrize(
    "changed,code",
    [
        ({"symbol": "XAUUSD"}, "mixed_candle_series"),
        ({"timeframe": "5m"}, "mixed_candle_series"),
        ({"time": START}, "duplicate_candle_timestamp"),
        ({"time": START - timedelta(minutes=1)}, "market_candle_out_of_order"),
        ({"time": START.replace(tzinfo=None)}, "market_candle_timestamp_invalid"),
        ({"high": Decimal(1)}, "market_candle_invalid"),
        ({"close": Decimal("NaN")}, "market_candle_invalid"),
    ],
)
def test_bad_input_series_is_rejected(changed: dict[str, Any], code: str) -> None:
    data = bars([10, 14, 10])
    data[1] = data[1].model_copy(update=changed)
    with pytest.raises(LonoraError, match=code):
        analyze(data)


def test_future_bar_is_rejected_even_within_shared_health_clock_skew() -> None:
    data = bars([10, 14, 10])
    with pytest.raises(LonoraError, match="market_candle_timestamp_future"):
        analyze(data, observed_at=data[-1].time - timedelta(seconds=1))


def test_empty_stale_oversized_and_live_only_inputs_fail_explicitly() -> None:
    with pytest.raises(LonoraError, match="market_candles_unavailable"):
        analyze([])
    data = bars([10, 14, 10])
    with pytest.raises(LonoraError, match="market_candles_stale"):
        analyze(data, observed_at=candle_close_time(data[-1].time, "1m") + timedelta(minutes=3))
    with pytest.raises(LonoraError, match="market_structure_candle_limit"):
        analyze(bars([10] * 1001))
    with pytest.raises(LonoraError, match="market_candles_unavailable"):
        analyze(data[:1], observed_at=START + timedelta(seconds=10))


def test_recent_live_bar_does_not_make_old_closed_evidence_fresh() -> None:
    data = bars([10, 14, 10])
    now = data[-1].time + timedelta(hours=2)
    live = data[-1].model_copy(update={"time": now})
    with pytest.raises(LonoraError, match="market_candles_stale"):
        analyze([*data, live], observed_at=now)


@pytest.mark.parametrize(
    "account_id,symbol,timeframe,code",
    [
        ("", "XAUUSDm", "1m", "market_structure_scope_invalid"),
        ("account", "", "1m", "market_structure_scope_invalid"),
        ("account", "XAUUSDm", "M1", "unsupported_timeframe"),
    ],
)
def test_missing_scope_and_unknown_timeframe_fail_explicitly(
    account_id: str, symbol: str, timeframe: str, code: str
) -> None:
    with pytest.raises(LonoraError, match=code):
        analyze_structure(
            bars([10, 14, 10]),
            account_id=account_id,
            symbol=symbol,
            timeframe=timeframe,
            observed_at=START + timedelta(minutes=3),
        )
