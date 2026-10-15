"""Versioned real-OHLC detector geometry and identical live/replay lifecycle."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from lonora_contracts.market import Candle, Quote
from lonora_contracts.market_intelligence import DetectorDefinition
from lonora_contracts.market_watch import Watch
from lonora_market.detectors import evaluate_detector
from lonora_market.watch_lifecycle import advance_watch
from pydantic import ValidationError

NOW = datetime(2026, 10, 15, 12, tzinfo=UTC)


def price(value: str, at: datetime = NOW) -> Quote:
    return Quote(
        symbol="XAUUSDm",
        bid=Decimal(value),
        ask=Decimal(value) + 1,
        observed_at=at,
        source="explicit-replay",
    )


def level() -> DetectorDefinition:
    return DetectorDefinition(
        id="entry",
        kind="level",
        level=Decimal(100),
        tolerance=Decimal(1),
        exit_tolerance=Decimal(2),
    )


def test_live_candle_is_forming_then_closes_or_invalidates() -> None:
    definition = DetectorDefinition(id="engulfing", kind="candle", pattern="bullish_engulfing")
    bars = [
        Candle(
            symbol="XAUUSDm",
            timeframe="15m",
            time=NOW - timedelta(minutes=15),
            open=Decimal(102),
            high=Decimal(103),
            low=Decimal(99),
            close=Decimal(100),
        ),
        Candle(
            symbol="XAUUSDm",
            timeframe="15m",
            time=NOW,
            open=Decimal(99),
            high=Decimal(104),
            low=Decimal(98),
            close=Decimal(103),
        ),
    ]
    forming = evaluate_detector(
        definition,
        symbol="XAUUSDm",
        timeframe="15m",
        quote=None,
        candles=bars,
        observed_at=NOW + timedelta(minutes=1),
    )
    assert forming.state == "forming" and forming.values["is_closed"] is False
    closed = evaluate_detector(
        definition,
        symbol="XAUUSDm",
        timeframe="15m",
        quote=None,
        candles=bars,
        observed_at=NOW + timedelta(minutes=15),
        previous=forming,
    )
    assert closed.state == "confirmed" and closed.detector_version == "1"
    corrected = [bars[0], bars[1].model_copy(update={"close": Decimal(98)})]
    invalidated = evaluate_detector(
        definition,
        symbol="XAUUSDm",
        timeframe="15m",
        quote=None,
        candles=corrected,
        observed_at=NOW + timedelta(minutes=15),
        previous=closed,
    )
    assert invalidated.state == "invalidated"


def test_trendline_projects_time_and_hysteresis_prevents_flapping() -> None:
    definition = DetectorDefinition.model_validate(
        {
            "id": "line",
            "kind": "trendline",
            "relation": "touch",
            "tolerance": "1",
            "exit_tolerance": "3",
            "anchors": [
                {"time": NOW - timedelta(hours=2), "price": "90"},
                {"time": NOW - timedelta(hours=1), "price": "100"},
            ],
        }
    )
    touched = evaluate_detector(
        definition,
        symbol="XAUUSDm",
        timeframe="1h",
        quote=price("110"),
        candles=[],
        observed_at=NOW,
    )
    assert touched.state == "confirmed" and touched.values["level"] == "110"
    held = evaluate_detector(
        definition,
        symbol="XAUUSDm",
        timeframe="1h",
        quote=price("112"),
        candles=[],
        observed_at=NOW,
        previous=touched,
    )
    assert held.state == "confirmed"
    broken = evaluate_detector(
        definition,
        symbol="XAUUSDm",
        timeframe="1h",
        quote=price("114"),
        candles=[],
        observed_at=NOW,
        previous=held,
    )
    assert broken.state == "invalidated"


@pytest.mark.parametrize(
    "operator,expected", [("all", "pending"), ("any", "confirmed"), ("not", "confirmed")]
)
def test_composites_and_missing_evidence(operator: str, expected: str) -> None:
    first = {"id": "lower", "kind": "level", "level": "90"}
    second = {"id": "higher", "kind": "level", "level": "110"}
    definition = DetectorDefinition.model_validate(
        {
            "id": "composite",
            "kind": operator,
            "children": [second] if operator == "not" else [first, second],
        }
    )
    result = evaluate_detector(
        definition,
        symbol="XAUUSDm",
        timeframe="1h",
        quote=price("100"),
        candles=[],
        observed_at=NOW,
    )
    if operator == "all":
        assert result.state == "forming"
    else:
        assert result.state == expected
    missing = evaluate_detector(
        definition, symbol="XAUUSDm", timeframe="1h", quote=None, candles=[], observed_at=NOW
    )
    assert missing.state != "confirmed"


def test_distinct_observations_debounce_expiry_and_replay() -> None:
    config = Watch(
        kind="dynamic",
        detector=level(),
        account_id="account",
        symbol="XAUUSDm",
        prompt="Revalidate",
        required_observations=2,
        debounce_seconds=2,
        confirmation_ttl_seconds=10,
    )
    state = {}
    transitions: list[tuple[str, bool]] = []
    for identity, seconds in [("a", 0), ("a", 1), ("b", 2)]:
        state, actionable = advance_watch(
            config,
            state,
            matched=True,
            observation_id=identity,
            observed_at=NOW + timedelta(seconds=seconds),
            now=NOW + timedelta(seconds=seconds),
        )
        transitions.append((state["lifecycle"], actionable))
    assert transitions == [("forming", False), ("forming", False), ("confirmed", True)]
    until = state["confirmation_valid_until"]
    state, _ = advance_watch(
        config,
        state,
        matched=True,
        observation_id="c",
        observed_at=NOW + timedelta(seconds=3),
        now=NOW + timedelta(seconds=3),
    )
    assert state["confirmation_valid_until"] == until
    expired, actionable = advance_watch(
        config,
        state,
        matched=True,
        observation_id="d",
        observed_at=NOW + timedelta(seconds=12),
        now=NOW + timedelta(seconds=12),
    )
    assert expired["lifecycle"] == "expired" and actionable is False
    # A new process reuses the same persisted state and cannot resurrect an expired signal.
    recovered, actionable = advance_watch(
        config,
        dict(expired),
        matched=True,
        observation_id="new",
        observed_at=NOW + timedelta(seconds=20),
        now=NOW + timedelta(seconds=20),
    )
    assert recovered["lifecycle"] == "expired" and actionable is False


def test_invalid_geometric_contracts_rejected() -> None:
    with pytest.raises(ValidationError):
        DetectorDefinition.model_validate(
            {
                "id": "bad",
                "kind": "trendline",
                "anchors": [{"time": NOW, "price": "100"}, {"time": NOW, "price": "101"}],
            }
        )
    with pytest.raises(ValidationError):
        DetectorDefinition.model_validate(
            {
                "id": "bad",
                "kind": "all",
                "children": [
                    {"id": "same", "kind": "level", "level": "1"},
                    {"id": "same", "kind": "level", "level": "2"},
                ],
            }
        )
