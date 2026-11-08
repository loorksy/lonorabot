"""Multi-timeframe snapshot facts from deterministic candles; pure, no broker or DB."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest
from lonora_contracts.domain import utcnow
from lonora_contracts.market import CalendarEvent, Candle, Quote
from lonora_core.user_error import LonoraError
from lonora_market.candles import CSV_COLUMNS, candles_csv
from lonora_market.economic_calendar import select_events
from lonora_market.snapshot import market_snapshot, summarize_timeframe
from lonora_market.watch_lifecycle import candle_close_time

NOW = datetime(2026, 3, 18, 12, 7, tzinfo=UTC)
STEP = {"15m": timedelta(minutes=15), "1h": timedelta(hours=1), "1d": timedelta(days=1)}


def series(
    closes: list[float], timeframe: str = "15m", *, spread: float = 1.0, last_open: datetime
) -> list[Candle]:
    """Bars ending with one that opened at `last_open`; each bar is close +/- spread."""
    result: list[Candle] = []
    for index, close in enumerate(closes):
        opened = last_open - STEP[timeframe] * (len(closes) - 1 - index)
        high, low = close + spread, close - spread
        result.append(
            Candle(
                symbol="XAUUSD",
                timeframe=timeframe,
                time=opened,
                open=Decimal(str(close)),
                high=Decimal(str(round(high, 2))),
                low=Decimal(str(round(low, 2))),
                close=Decimal(str(close)),
            )
        )
    return result


FORMING_15M = datetime(2026, 3, 18, 12, 0, tzinfo=UTC)


def summary(candles: list[Candle] | str, **kwargs: Any) -> dict[str, Any]:
    return summarize_timeframe(
        candles,
        account_id="acc",
        symbol="XAUUSD",
        timeframe=kwargs.pop("timeframe", "15m"),
        now=kwargs.pop("now", NOW),
        digits=2,
        **kwargs,
    )


def zigzag(count: int, *, rising: bool) -> list[float]:
    """Swings every 4 bars; each swing high/low is 3 points beyond the previous one."""
    pattern = [0, 4, 8, 4]
    direction = 1 if rising else -1
    return [2000 + direction * (index // 4) * 3 + pattern[index % 4] for index in range(count)]


def test_forming_bar_is_reported_and_excluded() -> None:
    bars = series([float(2000 + i) for i in range(60)], last_open=FORMING_15M)
    result = summary(bars)
    assert result["available"] and result["closed_bars"] == 59
    assert result["last_closed_bar"]["opened_at"] == "2026-03-18T11:45:00+00:00"
    assert result["last_closed_bar"]["closed_at"] == "2026-03-18T12:00:00+00:00"
    assert result["forming_bar"] == {
        "opened_at": "2026-03-18T12:00:00+00:00",
        "closes_at": "2026-03-18T12:15:00+00:00",
        "high": str(bars[-1].high),
        "low": str(bars[-1].low),
        "last": str(bars[-1].close),
        "unfinished": True,
    }
    assert result["last_closed_bar"]["close"] == str(bars[-2].close)
    assert result["trend"]["label"] == "rising" and result["trend"]["change_atr"] > 1
    assert result["freshness"] == "healthy"


def test_cutoff_keeps_a_bar_closed_during_the_read_forming() -> None:
    bars = series([float(2000 + i) for i in range(60)], last_open=FORMING_15M)
    late = candle_close_time(FORMING_15M, "15m") + timedelta(seconds=5)
    assert summary(bars, now=late)["closed_bars"] == 60
    guarded = summary(bars, now=late, cutoff=late - timedelta(seconds=10))
    assert guarded["closed_bars"] == 59 and guarded["forming_bar"]["unfinished"]


@pytest.mark.parametrize(
    ("rising", "label"),
    [(True, "higher_high_higher_low"), (False, "lower_high_lower_low")],
)
def test_swing_structure_labels(rising: bool, label: str) -> None:
    result = summary(series(zigzag(41, rising=rising), last_open=FORMING_15M), swing_bars=1)
    structure = result["structure"]
    assert structure["label"] == label
    high, previous = structure["last_swing_high"], structure["previous_swing_high"]
    assert (Decimal(high["price"]) > Decimal(previous["price"])) is rising
    assert high["confirmed_at"] > high["time"]


def test_volatility_regime_is_mid_rank_percentile() -> None:
    flat = summary(series([2000.0] * 150, spread=1.0, last_open=FORMING_15M))
    assert flat["volatility"]["regime"] == "normal"
    assert flat["volatility"]["atr_percentile"] == 50.0
    assert flat["trend"]["label"] == "flat" and flat["rsi"]["value"] == 50.0
    expanding = summary(
        series([2000.0] * 140 + [2000.0] * 9 + [2000.0], spread=1.0, last_open=FORMING_15M)[:-10]
        + series([2000.0] * 10, spread=9.0, last_open=FORMING_15M)
    )
    assert expanding["volatility"]["regime"] == "high"
    assert expanding["volatility"]["atr_percentile"] > 95
    short = summary(series([2000.0] * 20, last_open=FORMING_15M))
    assert short["volatility"]["regime"] == "insufficient_history"


def test_unavailable_invalid_and_stale_inputs_stay_explicit() -> None:
    assert summary("unsupported_timeframe") == {
        "timeframe": "15m",
        "available": False,
        "reason": "unsupported_timeframe",
    }
    bars = series([2000.0, 2001.0, 2002.0], last_open=FORMING_15M)
    duplicate = [*bars, bars[-1]]
    assert summary(duplicate)["reason"] == "duplicate_candle_timestamp"
    stale = summary(bars, now=NOW + timedelta(days=3))
    assert stale["available"] and stale["freshness"] == "stale"
    future = summary(series([2000.0, 2001.0], last_open=NOW + timedelta(minutes=30)))
    assert future["reason"] == "market_candles_timestamp_future"


def daily() -> list[Candle]:
    return series(
        [2000.0 + 10 * i for i in range(30)],
        "1d",
        spread=5.0,
        last_open=datetime(2026, 3, 18, tzinfo=UTC),
    )


def snapshot(quote: Quote | str, **kwargs: Any) -> dict[str, Any]:
    frames = {
        "15m": series([2280.0 + i * 0.5 for i in range(120)], last_open=FORMING_15M),
        "1h": "market_history_timeout",
    }
    return market_snapshot(
        account_id="acc",
        symbol="XAUUSD",
        now=kwargs.pop("now", NOW),
        digits=2,
        tick_size=Decimal("0.01"),
        quote=quote,
        timeframes=frames,
        daily=daily(),
        weekly=kwargs.pop("weekly", "unsupported_timeframe"),
        **kwargs,
    )


def test_snapshot_levels_distances_and_quote() -> None:
    quote = Quote(
        symbol="XAUUSD",
        bid=Decimal("2290.00"),
        ask=Decimal("2290.40"),
        observed_at=NOW - timedelta(seconds=2),
        source="fixture",
    )
    result = snapshot(quote)
    assert result["execution_authorized"] is False
    assert result["quote"]["spread"] == "0.40" and result["quote"]["spread_ticks"] == 40.0
    assert result["quote"]["freshness"] == "healthy"
    assert result["reference_price"] == "2290.20" and result["reference_basis"] == "quote_mid"
    assert result["timeframes"][1] == {
        "timeframe": "1h",
        "available": False,
        "reason": "market_history_timeout",
    }
    levels = result["levels"]
    previous = daily()[-2]
    assert levels["previous_day"]["high"] == str(previous.high)
    assert levels["previous_week"] == {"available": False, "reason": "unsupported_timeframe"}
    day_high = next(item for item in levels["distances"] if item["level"] == "previous_day_high")
    distance = float(previous.high - Decimal("2290.20"))
    assert day_high["distance"] == round(distance, 3)
    assert day_high["distance_atr"] == round(distance / levels["daily_atr"], 2)
    assert day_high["side"] == ("above" if distance > 0 else "below")
    names = [item["level"] for item in levels["distances"]]
    assert "current_day_high_so_far" in names and "current_day_low_so_far" in names
    assert result["data_freshness"] == "unavailable"  # 1h could not be read.


def test_snapshot_without_quote_uses_last_closed_close() -> None:
    result = snapshot("quote_unavailable")
    assert result["quote"] == {"available": False, "reason": "quote_unavailable"}
    assert result["reference_basis"] == "15m_last_closed_close"
    stale = Quote(
        symbol="XAUUSD",
        bid=Decimal("2290"),
        ask=Decimal("2291"),
        observed_at=NOW - timedelta(minutes=30),
        source="fixture",
    )
    assert snapshot(stale)["reference_basis"] == "stale_quote_mid"
    with pytest.raises(LonoraError):
        snapshot(stale, now=datetime(2026, 3, 18, 12, 7))
    with pytest.raises(LonoraError):
        snapshot(stale, bars_read_at=NOW + timedelta(seconds=1))


def test_csv_is_exact_and_marks_closed_rows() -> None:
    bars = series([2000.12, 2000.5], last_open=FORMING_15M)
    body = candles_csv(bars, [True, False], ["c1", "c2"]).decode()
    lines = body.splitlines()
    assert lines[0] == ",".join(CSV_COLUMNS)
    assert lines[1].split(",")[5] == "2000.12" and lines[1].endswith(",1")
    assert lines[2].endswith(",0") and len(lines) == 3


def event(identifier: str, minutes: int, **extra: Any) -> CalendarEvent:
    now = utcnow()
    return CalendarEvent.model_validate(
        {
            "id": identifier,
            "name": "Event " + identifier,
            "currency": extra.pop("currency", "USD"),
            "observed_at": now,
            "scheduled_at": now + timedelta(minutes=minutes),
            "impact": extra.pop("impact", "High"),
            "source": "fixture",
            **extra,
        }
    )


def test_calendar_window_filters_and_statuses() -> None:
    now = utcnow()
    events = [
        ("cal-1", event("cpi", 90, forecast="3.1%")),
        ("cal-1", event("nfp", -30, actual="250K")),
        ("cal-1", event("late", -10)),
        ("cal-1", event("ecb", 60, currency="EUR", impact="Medium")),
        ("cal-2", event("old", -60 * 30)),
        ("cal-2", event("far", 60 * 100)),
    ]
    page, total = select_events(
        events,
        now=now,
        hours_back=12,
        hours_ahead=48,
        currencies={"USD"},
        impacts={"high"},
        limit=2,
    )
    assert total == 3 and [item["id"] for item in page] == ["nfp", "late"]
    assert page[0]["status"] == "released" and page[1]["status"] == "due_without_actual"
    assert page[0]["integration_id"] == "cal-1" and page[0]["minutes_from_now"] < 0
    every, total = select_events(
        events, now=now, hours_back=12, hours_ahead=48, currencies=set(), impacts=set(), limit=50
    )
    assert total == 4 and {item["id"] for item in every} == {"cpi", "nfp", "late", "ecb"}
    assert next(item for item in every if item["id"] == "cpi")["status"] == "upcoming"
