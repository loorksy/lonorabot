"""Measured relationship tests use aligned synthetic histories, never live money."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from math import cos, exp, isclose, pi, sin

import pytest
from lonora_contracts.market import Candle
from lonora_contracts.relationships import RelationshipRequest
from lonora_core.chart_controller import TIMEFRAMES
from lonora_market.relationships import bar_end, measure_relationship, pearson


def series(timeframe: str = "1m", *, inverted: bool = False) -> tuple[list[list[Candle]], datetime]:
    values: list[list[Candle]] = [[], []]
    time = datetime(2024, 1, 1, tzinfo=UTC)
    prices = [100.0, 200.0]
    for index in range(62):
        change = 0.001 * (sin(index * 1.7) + 0.4 * sin(index * 0.3))
        for side in range(2):
            sign = -1 if inverted and side == 1 and index > 30 else 1
            prices[side] *= exp(change * sign)
            price = Decimal(str(prices[side]))
            values[side].append(
                Candle(
                    symbol=["EURUSDm", "XAUUSD.raw"][side],
                    timeframe=timeframe,
                    time=time,
                    open=price,
                    high=price,
                    low=price,
                    close=price,
                )
            )
        if index != 61:
            time = bar_end(time, timeframe)
    return values, time + timedelta(seconds=10)


def measured(values: list[list[Candle]], now: datetime):
    return measure_relationship(
        RelationshipRequest(
            account_id="account",
            symbols=["EURUSDm", "XAUUSD.raw"],
            timeframe=values[0][0].timeframe,
        ),
        values,
        identifier="relationship",
        owner_id="owner",
        agent_id="agent",
        now=now,
    )


@pytest.mark.parametrize("timeframe", sorted(TIMEFRAMES))
def test_all_timeframes_exact_symbols_closed_returns_and_reproducibility(timeframe: str):
    values, now = series(timeframe)
    result = measured(values, now)
    assert result.available and result.state == "stable"
    assert result.sample_count == result.baseline_count == 30
    assert result.correlation is not None and isclose(result.correlation, 1, abs_tol=1e-10)
    assert result.alignment_ratio == 1
    assert result.valid_until and result.valid_until > now
    assert result.symbols == ["EURUSDm", "XAUUSD.raw"]
    assert result.causal_claim is result.execution_authorized is False
    assert pearson(result.samples[-30:]) == result.correlation
    # A changing open bar cannot change the closed-bar metric.
    values[1][-1] = values[1][-1].model_copy(
        update={
            "open": Decimal(999),
            "high": Decimal(999),
            "low": Decimal(999),
            "close": Decimal(999),
        }
    )
    assert measured(values, now).correlation == result.correlation


def test_recent_relationship_can_invert_against_disjoint_baseline():
    values, now = series(inverted=True)
    result = measured(values, now)
    assert result.state == "inverted"
    assert result.baseline_correlation is not None and isclose(
        result.baseline_correlation, 1, abs_tol=1e-10
    )
    assert result.correlation is not None and isclose(result.correlation, -1, abs_tol=1e-10)
    assert result.samples[29].end < result.samples[30].end


@pytest.mark.parametrize(("weight", "state"), [(0.0, "breaking"), (0.6, "weakening")])
def test_measured_strength_change(weight: float, state: str):
    values, now = series()
    prices = [100.0, 200.0]
    for index in range(62):
        angle = (index - 1) * 2 * pi / 30
        left = sin(angle)
        right = left if index <= 30 else weight * left + (1 - weight**2) ** 0.5 * cos(angle)
        for side, change in enumerate((left, right)):
            prices[side] *= exp(change * 0.001)
            values[side][index] = values[side][index].model_copy(
                update={key: Decimal(str(prices[side])) for key in ("open", "high", "low", "close")}
            )
    result = measured(values, now)
    assert result.state == state
    assert result.baseline_correlation is not None and isclose(
        result.baseline_correlation, 1, abs_tol=1e-10
    )
    assert result.correlation is not None and isclose(result.correlation, weight, abs_tol=1e-10)


def test_asymmetric_gaps_do_not_get_forward_filled_or_index_aligned():
    values, now = series()
    values[1] = [bar for index, bar in enumerate(values[1]) if index % 3 != 0]
    result = measured(values, now)
    assert result.state in {"unreliable", "unavailable"}
    assert all((sample.end - sample.start).total_seconds() == 60 for sample in result.samples)
    assert result.sample_count < 30 and result.alignment_ratio < 0.8


def test_stale_missing_duplicate_and_flat_data_remain_unavailable():
    values, now = series()
    assert measured(values, now + timedelta(hours=1)).state == "unavailable"
    assert measured([values[0], []], now).state == "unavailable"
    assert measured([values[0], values[1] + [values[1][-1]]], now).state == "unavailable"
    flat = [
        bar.model_copy(update={key: Decimal(100) for key in ("open", "high", "low", "close")})
        for bar in values[1]
    ]
    result = measured([values[0], flat], now)
    assert result.correlation is None and not result.available


def test_calendar_month_end_handles_december_and_leap_year():
    assert bar_end(datetime(2023, 12, 1, tzinfo=UTC), "1mn") == datetime(2024, 1, 1, tzinfo=UTC)
    assert bar_end(datetime(2024, 2, 1, tzinfo=UTC), "1mn") == datetime(2024, 3, 1, tzinfo=UTC)
