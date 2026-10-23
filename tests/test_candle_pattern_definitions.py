"""Offline acceptance for the six advertised OHLC definitions, not trade signals.

Engulfing compares inclusive body bounds and opposite nonzero body directions.
Inside bars require strict high/low containment. Doji uses an inclusive body/range
threshold. Pins require a dominant wick at least twice the body and opposite wick,
and the matching body direction (a zero body is permitted by the definition).
"""

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Literal

import pytest
from lonora_contracts.market import Candle
from lonora_contracts.market_intelligence import DetectorDefinition, Observation
from lonora_market.detectors import evaluate_detector

type Pattern = Literal[
    "bullish_engulfing", "bearish_engulfing", "doji", "inside_bar", "bullish_pin", "bearish_pin"
]
type OHLC = tuple[str, str, str, str]

OPENED = datetime(2026, 10, 23, 12, tzinfo=UTC)
CLOSED = OPENED + timedelta(minutes=15)


@dataclass(frozen=True)
class Example:
    pattern: Pattern
    prior: OHLC
    matched: OHLC
    unmatched: OHLC
    required: int


EXAMPLES = [
    Example(
        "bullish_engulfing",
        ("103", "104", "99", "100"),
        ("99", "105", "98", "104"),
        ("101", "104", "99", "102"),
        2,
    ),
    Example(
        "bearish_engulfing",
        ("100", "104", "99", "103"),
        ("104", "105", "98", "99"),
        ("102", "104", "99", "101"),
        2,
    ),
    Example(
        "doji",
        ("100", "105", "95", "101"),
        ("100", "105", "95", "101"),
        ("100", "105", "95", "101.01"),
        1,
    ),
    Example(
        "inside_bar",
        ("100", "110", "90", "105"),
        ("101", "109", "91", "102"),
        ("101", "110", "91", "102"),
        2,
    ),
    Example(
        "bullish_pin",
        ("100", "105", "95", "101"),
        ("100", "102", "96", "102"),
        ("100", "102", "96.01", "102"),
        1,
    ),
    Example(
        "bearish_pin",
        ("100", "105", "95", "101"),
        ("102", "106", "100", "100"),
        ("102", "105.99", "100", "100"),
        1,
    ),
]


def bar(values: OHLC, *, opened: datetime = OPENED, scale: str = "1") -> Candle:
    multiplier = Decimal(scale)
    return Candle(
        symbol="EURUSD.suffix",
        timeframe="15m",
        time=opened,
        open=Decimal(values[0]) * multiplier,
        high=Decimal(values[1]) * multiplier,
        low=Decimal(values[2]) * multiplier,
        close=Decimal(values[3]) * multiplier,
    )


def series(example: Example, *, matched: bool = True, scale: str = "1") -> list[Candle]:
    current = bar(example.matched if matched else example.unmatched, scale=scale)
    if example.required == 1:
        return [current]
    return [bar(example.prior, opened=OPENED - timedelta(minutes=15), scale=scale), current]


def evaluate(
    pattern: Pattern,
    candles: list[Candle],
    *,
    at: datetime = CLOSED,
    previous: Observation | None = None,
    body_ratio: str = "0.1",
) -> Observation:
    return evaluate_detector(
        DetectorDefinition(
            id="accepted-definition",
            kind="candle",
            pattern=pattern,
            body_ratio=Decimal(body_ratio),
        ),
        symbol="EURUSD.suffix",
        timeframe="15m",
        quote=None,
        candles=candles,
        observed_at=at,
        previous=previous,
    )


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.pattern)
def test_each_definition_confirms_only_on_actual_close_and_replays_identically(
    example: Example,
) -> None:
    candles = series(example)
    forming = evaluate(example.pattern, candles, at=CLOSED - timedelta(microseconds=1))
    assert forming.state == "forming"
    assert forming.values["matched"] is None
    assert forming.values["is_closed"] is False
    assert forming.observed_at == OPENED

    closed = evaluate(example.pattern, candles, previous=forming)
    assert closed.state == "confirmed"
    assert closed.values["matched"] is True
    assert closed.values["is_closed"] is True
    assert closed.values["pattern"] == example.pattern
    assert closed.observed_at == CLOSED
    assert closed.symbol == "EURUSD.suffix" and closed.timeframe == "15m"
    assert closed.source == "broker_ohlc" and closed.detector_version == "1"
    assert len(closed.values["bars"]) == example.required
    assert evaluate(example.pattern, candles).model_dump() == closed.model_dump()


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.pattern)
def test_negative_definition_and_corrected_ohlc_invalidate_prior_confirmation(
    example: Example,
) -> None:
    confirmed = evaluate(example.pattern, series(example))
    corrected = series(example, matched=False)
    unmatched = evaluate(example.pattern, corrected)
    assert unmatched.state == "pending" and unmatched.values["matched"] is False

    invalidated = evaluate(example.pattern, corrected, previous=confirmed)
    assert invalidated.state == "invalidated"
    assert invalidated.values["matched"] is False
    assert invalidated.id != confirmed.id
    assert invalidated.values["bars"][-1] == corrected[-1].model_dump(mode="json")


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.pattern)
def test_definitions_preserve_decimal_scale_instead_of_assuming_pips(example: Example) -> None:
    actual = evaluate(example.pattern, series(example, scale="0.00001"))
    assert actual.state == "confirmed"
    assert Decimal(actual.values["bars"][-1]["open"]) == Decimal(example.matched[0]) / 100000


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.pattern)
def test_missing_bars_are_pending_not_negated_evidence(example: Example) -> None:
    enough = series(example)
    for count in range(example.required):
        result = evaluate(example.pattern, enough[:count])
        assert result.state == "pending"
        assert result.values == {
            "missing": ["candles"],
            "required_bars": example.required,
            "available_bars": count,
        }


@pytest.mark.parametrize("example", EXAMPLES, ids=lambda example: example.pattern)
def test_identical_flat_bars_never_confirm_any_advertised_pattern(example: Example) -> None:
    candles = [
        bar(("100", "100", "100", "100"), opened=OPENED - timedelta(minutes=15)),
        bar(("100", "100", "100", "100")),
    ]
    result = evaluate(example.pattern, candles)
    assert result.state == "pending" and result.values["matched"] is False


@pytest.mark.parametrize(
    "pattern,prior,current,matched",
    [
        # Equal body endpoints count, but prior doji/same direction do not.
        ("bullish_engulfing", ("103", "104", "99", "100"), ("100", "104", "99", "103"), True),
        ("bullish_engulfing", ("103", "104", "99", "100"), ("100.01", "104", "99", "103"), False),
        ("bullish_engulfing", ("100", "104", "99", "100"), ("99", "104", "98", "103"), False),
        ("bullish_engulfing", ("100", "104", "99", "103"), ("99", "105", "98", "104"), False),
        ("bearish_engulfing", ("100", "104", "99", "103"), ("103", "104", "99", "100"), True),
        ("bearish_engulfing", ("100", "104", "99", "103"), ("102.99", "104", "99", "100"), False),
        ("bearish_engulfing", ("100", "104", "99", "100"), ("103", "104", "98", "99"), False),
        ("bearish_engulfing", ("103", "104", "99", "100"), ("104", "105", "98", "99"), False),
        # Inside means strict containment; equal high or equal low is excluded.
        ("inside_bar", ("100", "110", "90", "105"), ("101", "109.99", "90.01", "102"), True),
        ("inside_bar", ("100", "110", "90", "105"), ("101", "110", "90.01", "102"), False),
        ("inside_bar", ("100", "110", "90", "105"), ("101", "109.99", "90", "102"), False),
    ],
)
def test_two_bar_definition_boundaries(
    pattern: Pattern, prior: OHLC, current: OHLC, matched: bool
) -> None:
    actual = evaluate(
        pattern,
        [bar(prior, opened=OPENED - timedelta(minutes=15)), bar(current)],
    )
    assert actual.values["matched"] is matched


@pytest.mark.parametrize(
    "current,ratio,matched",
    [
        (("100", "105", "95", "101"), "0.1", True),
        (("100", "105", "95", "101.00001"), "0.1", False),
        (("100", "105", "95", "99"), "0.1", True),
        (("100", "105", "95", "100"), "0.1", True),
        (("100", "100", "100", "100"), "0.1", False),
        (("100", "105", "95", "102"), "0.2", True),
        (("100", "105", "95", "102"), "0.19999", False),
    ],
)
def test_doji_uses_nonzero_range_and_explicit_inclusive_decimal_ratio(
    current: OHLC, ratio: str, matched: bool
) -> None:
    assert evaluate("doji", [bar(current)], body_ratio=ratio).values["matched"] is matched


@pytest.mark.parametrize(
    "pattern,current,matched",
    [
        ("bullish_pin", ("100", "102", "96", "102"), True),
        ("bullish_pin", ("100", "102", "96.00001", "102"), False),
        ("bullish_pin", ("100", "103", "96", "101"), True),
        ("bullish_pin", ("100", "103.00001", "96", "101"), False),
        ("bullish_pin", ("101", "102", "96", "100"), False),
        ("bullish_pin", ("100", "100", "96", "100"), True),
        ("bullish_pin", ("100", "104", "100", "100"), False),
        ("bearish_pin", ("102", "106", "100", "100"), True),
        ("bearish_pin", ("102", "105.99999", "100", "100"), False),
        ("bearish_pin", ("101", "105", "98", "100"), True),
        ("bearish_pin", ("101", "105", "97.99999", "100"), False),
        ("bearish_pin", ("100", "106", "99", "101"), False),
        ("bearish_pin", ("100", "104", "100", "100"), True),
        ("bearish_pin", ("100", "100", "96", "100"), False),
    ],
)
def test_pin_body_direction_and_two_to_one_wick_boundaries(
    pattern: Pattern, current: OHLC, matched: bool
) -> None:
    assert evaluate(pattern, [bar(current)]).values["matched"] is matched
