"""Compact multi-timeframe market facts from closed broker bars, never trade signals.

Every number is measured from supplied broker data. A forming bar is reported
separately and excluded from all calculations. Labels describe what was measured
(rising, flat, high volatility); they do not recommend, rank or authorize trades.
"""

from datetime import datetime
from decimal import Decimal
from typing import Any

from lonora_charts.indicators import indicator_series
from lonora_contracts.market import Candle, Quote
from lonora_core.user_error import LonoraError

from .health import assess_candles, assess_quote, timeframe_age_seconds
from .structure import SwingPoint, swing_points
from .watch_lifecycle import candle_close_time

METHODOLOGY = "closed_bar_market_snapshot_v1"
QUOTE_MAXIMUM_AGE_SECONDS = 120.0
_STATE_ORDER = {"healthy": 0, "stale": 1, "degraded": 2, "unavailable": 3}

TimeframeInput = list[Candle] | str  # Broker bars, or the error code that prevented reading them.


def _round(value: float | None, places: int) -> float | None:
    return None if value is None else round(value, places)


def _closed(candles: list[Candle], timeframe: str, now: datetime) -> list[Candle]:
    return [bar for bar in candles if candle_close_time(bar.time, timeframe) <= now]


def _slope(values: list[float]) -> float:
    """Least-squares change per bar; deterministic and independent of price scale."""
    count = len(values)
    mean_x = (count - 1) / 2
    mean_y = sum(values) / count
    denominator = sum((index - mean_x) ** 2 for index in range(count))
    return (
        sum((index - mean_x) * (value - mean_y) for index, value in enumerate(values)) / denominator
    )


def _compare(current: Decimal, previous: Decimal, up: str, down: str) -> str:
    return up if current > previous else down if current < previous else "equal"


def _swing(point: SwingPoint | None) -> dict[str, Any] | None:
    if point is None:
        return None
    return {
        "price": str(point.price),
        "time": point.time.isoformat(),
        "confirmed_at": point.available_at.isoformat(),
    }


def _structure(closed: list[Candle], swing_bars: int) -> dict[str, Any]:
    points = swing_points(closed, left_bars=swing_bars, right_bars=swing_bars)
    highs = [point for point in points if point.side == "high"]
    lows = [point for point in points if point.side == "low"]
    result: dict[str, Any] = {
        "swing_bars": swing_bars,
        "last_swing_high": _swing(highs[-1] if highs else None),
        "previous_swing_high": _swing(highs[-2] if len(highs) > 1 else None),
        "last_swing_low": _swing(lows[-1] if lows else None),
        "previous_swing_low": _swing(lows[-2] if len(lows) > 1 else None),
    }
    if len(highs) > 1 and len(lows) > 1:
        high = _compare(highs[-1].price, highs[-2].price, "higher_high", "lower_high")
        low = _compare(lows[-1].price, lows[-2].price, "higher_low", "lower_low")
        result["label"] = high + "_" + low
    else:
        result["label"] = "insufficient_swings"
    last = closed[-1].close
    result["last_close_beyond"] = (
        "above_last_swing_high"
        if highs and last > highs[-1].price
        else "below_last_swing_low"
        if lows and last < lows[-1].price
        else None
    )
    return result


def _percentile(values: list[float], current: float) -> float:
    """Mid-rank percentile: a constant history places the current value at 50, not 100."""
    below = sum(1 for value in values if value < current)
    equal = sum(1 for value in values if value == current)
    return 100 * (below + equal / 2) / len(values)


def summarize_timeframe(
    candles: TimeframeInput,
    *,
    account_id: str,
    symbol: str,
    timeframe: str,
    now: datetime,
    digits: int,
    swing_bars: int = 2,
    trend_bars: int = 20,
    atr_period: int = 14,
    rsi_period: int = 14,
    percentile_window: int = 100,
    cutoff: datetime | None = None,
) -> dict[str, Any]:
    """Facts for one timeframe; unreadable or invalid input stays explicitly unavailable.

    `cutoff` is when the bars were requested: only a bar that had closed by then is
    closed. A bar that closed while the read was in flight may hold partial data.
    """
    if isinstance(candles, str):
        return {"timeframe": timeframe, "available": False, "reason": candles}
    health = assess_candles(
        candles,
        account_id=account_id,
        symbol=symbol,
        timeframe=timeframe,
        now=now,
        maximum_age_seconds=timeframe_age_seconds(timeframe),
    )
    if health.state in {"degraded", "unavailable"}:
        return {"timeframe": timeframe, "available": False, "reason": health.reason_code}
    if any(bar.time > now for bar in candles):
        return {
            "timeframe": timeframe,
            "available": False,
            "reason": "market_candle_timestamp_future",
        }
    closed = _closed(candles, timeframe, cutoff or now)
    forming = candles[len(closed) :]
    if len(closed) < 2:
        return {"timeframe": timeframe, "available": False, "reason": "insufficient_closed_bars"}
    last = closed[-1]
    closes = [float(bar.close) for bar in closed]
    atr_values = indicator_series("atr", closed, atr_period)["value"]
    atr = atr_values[-1]
    rsi_values = indicator_series("rsi", closed, rsi_period)["value"]
    window = closed[-trend_bars:]
    high, low = max(bar.high for bar in window), min(bar.low for bar in window)
    size = float(high - low)
    change = _slope([float(bar.close) for bar in window]) * (len(window) - 1)
    change_atr = change / atr if atr else None
    history = [value for value in atr_values[-percentile_window:] if value is not None]
    percentile = _percentile(history, atr) if atr is not None and history else None
    regime = (
        "insufficient_history"
        if percentile is None or len(history) < 20
        else "high"
        if percentile >= 80
        else "low"
        if percentile <= 20
        else "normal"
    )
    places = digits + 1
    result: dict[str, Any] = {
        "timeframe": timeframe,
        "available": True,
        "freshness": health.state,
        "closed_bars": len(closed),
        "last_closed_bar": {
            "opened_at": last.time.isoformat(),
            "closed_at": candle_close_time(last.time, timeframe).isoformat(),
            "close": str(last.close),
        },
        "trend": {
            "bars": len(window),
            "regression_change": _round(change, places),
            "change_atr": _round(change_atr, 2),
            "label": "insufficient_history"
            if change_atr is None or len(window) < 5
            else "rising"
            if change_atr >= 1
            else "falling"
            if change_atr <= -1
            else "flat",
        },
        "structure": _structure(closed, swing_bars),
        "range": {
            "bars": len(window),
            "high": str(high),
            "low": str(low),
            "size_atr": _round(size / atr, 2) if atr else None,
            "close_position": _round(float(last.close - low) / size, 2) if size else None,
        },
        "volatility": {
            "atr": _round(atr, places),
            "atr_period": atr_period,
            "atr_method": "simple_mean_true_range",
            "atr_percentile": _round(percentile, 1),
            "percentile_sample": len(history),
            "regime": regime,
        },
        "rsi": {"period": rsi_period, "value": _round(rsi_values[-1], 1)},
        "last_close_change_atr": _round((closes[-1] - closes[-2]) / atr, 2) if atr else None,
    }
    if forming:
        bar = forming[-1]
        result["forming_bar"] = {
            "opened_at": bar.time.isoformat(),
            "closes_at": candle_close_time(bar.time, timeframe).isoformat(),
            "high": str(bar.high),
            "low": str(bar.low),
            "last": str(bar.close),
            "unfinished": True,
        }
    return result


def _level(
    name: str, price: Decimal, reference: Decimal, atr: float | None, digits: int
) -> dict[str, Any]:
    distance = float(price - reference)
    return {
        "level": name,
        "price": str(price),
        "distance": _round(distance, digits + 1),
        "distance_atr": _round(distance / atr, 2) if atr else None,
        "side": "above" if price > reference else "below" if price < reference else "at",
    }


def _period_levels(
    label: str, candles: TimeframeInput, timeframe: str, cutoff: datetime
) -> tuple[list[tuple[str, Decimal]], dict[str, Any]]:
    if isinstance(candles, str):
        return [], {"available": False, "reason": candles}
    closed = _closed(candles, timeframe, cutoff)
    if not closed:
        return [], {"available": False, "reason": "insufficient_closed_bars"}
    previous = closed[-1]
    info: dict[str, Any] = {
        "available": True,
        "bar_opened_at": previous.time.isoformat(),
        "high": str(previous.high),
        "low": str(previous.low),
    }
    levels = [("previous_" + label + "_high", previous.high)]
    levels.append(("previous_" + label + "_low", previous.low))
    return levels, info


def market_snapshot(
    *,
    account_id: str,
    symbol: str,
    now: datetime,
    digits: int,
    tick_size: Decimal | None,
    quote: Quote | str,
    timeframes: dict[str, TimeframeInput],
    daily: TimeframeInput,
    weekly: TimeframeInput,
    swing_bars: int = 2,
    trend_bars: int = 20,
    atr_period: int = 14,
    rsi_period: int = 14,
    bars_read_at: datetime | None = None,
) -> dict[str, Any]:
    if now.tzinfo is None or now.utcoffset() is None:
        raise LonoraError("market_snapshot_timestamp_invalid", 422)
    cutoff = bars_read_at or now
    if cutoff.tzinfo is None or cutoff.utcoffset() is None or cutoff > now:
        raise LonoraError("market_snapshot_timestamp_invalid", 422)
    summaries = [
        summarize_timeframe(
            candles,
            account_id=account_id,
            symbol=symbol,
            timeframe=timeframe,
            now=now,
            digits=digits,
            swing_bars=swing_bars,
            trend_bars=trend_bars,
            atr_period=atr_period,
            rsi_period=rsi_period,
            cutoff=cutoff,
        )
        for timeframe, candles in timeframes.items()
    ]
    quote_data: dict[str, Any]
    reference: Decimal | None = None
    reference_basis: str | None = None
    if isinstance(quote, str):
        quote_data = {"available": False, "reason": quote}
    else:
        health = assess_quote(
            quote,
            account_id=account_id,
            symbol=symbol,
            now=now,
            maximum_age_seconds=QUOTE_MAXIMUM_AGE_SECONDS,
        )
        spread = quote.ask - quote.bid
        quote_data = {
            "available": health.state in {"healthy", "stale"},
            "freshness": health.state,
            "reason": None if health.healthy else health.reason_code,
            "bid": str(quote.bid),
            "ask": str(quote.ask),
            "spread": str(spread),
            "spread_ticks": float(spread / tick_size) if tick_size else None,
            "observed_at": quote.observed_at.isoformat(),
            "age_seconds": round((now - quote.observed_at).total_seconds(), 1),
        }
        if health.state in {"healthy", "stale"}:
            reference = (quote.bid + quote.ask) / 2
            reference_basis = "quote_mid" if health.healthy else "stale_quote_mid"
    if reference is None:
        for summary in summaries:
            if summary.get("available"):
                reference = Decimal(summary["last_closed_bar"]["close"])
                reference_basis = summary["timeframe"] + "_last_closed_close"
                break
    daily_summary = summarize_timeframe(
        daily,
        account_id=account_id,
        symbol=symbol,
        timeframe="1d",
        now=now,
        digits=digits,
        atr_period=atr_period,
        rsi_period=rsi_period,
        cutoff=cutoff,
    )
    daily_atr = daily_summary["volatility"]["atr"] if daily_summary.get("available") else None
    day_levels, day_info = _period_levels("day", daily, "1d", cutoff)
    week_levels, week_info = _period_levels("week", weekly, "1w", cutoff)
    if isinstance(daily, list):
        forming = [bar for bar in daily if candle_close_time(bar.time, "1d") > cutoff]
        if forming and forming[-1].time <= now:
            day_levels += [
                ("current_day_high_so_far", forming[-1].high),
                ("current_day_low_so_far", forming[-1].low),
            ]
    levels = (
        [
            _level(name, price, reference, daily_atr, digits)
            for name, price in day_levels + week_levels
        ]
        if reference is not None
        else []
    )
    states = [summary.get("freshness", "unavailable") for summary in summaries]
    states.append(quote_data.get("freshness", "unavailable"))
    return {
        "methodology": METHODOLOGY,
        "account_id": account_id,
        "symbol": symbol,
        "observed_at": now.isoformat(),
        "bars_requested_at": cutoff.isoformat(),
        "data_freshness": max(states, key=lambda state: _STATE_ORDER.get(state, 3)),
        "quote": quote_data,
        "reference_price": str(reference) if reference is not None else None,
        "reference_basis": reference_basis,
        "timeframes": summaries,
        "levels": {
            "previous_day": day_info,
            "previous_week": week_info,
            "atr_basis": "1d" if daily_atr else None,
            "daily_atr": daily_atr,
            "distances": levels,
        },
        "execution_authorized": False,
        "limitations": [
            "Measured from broker bars only; forming bars are excluded from every calculation.",
            "Daily and weekly bars follow the broker server's day boundary.",
            "Labels describe measurements, not entry signals or forecasts.",
        ],
    }
