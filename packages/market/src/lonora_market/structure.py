"""Bounded closed-bar swing facts and alternative lines, never trading decisions.

Windows count supplied bars, not presumed broker sessions. A swing is knowable
only when its final right-hand confirming bar closes. Strict comparisons reject
equal extrema; no currently forming or future bar can supply confirmation.
"""

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, DecimalException, localcontext
from itertools import combinations
from typing import Any, Literal

from lonora_contracts.market import Candle
from lonora_contracts.market_intelligence import Observation, ObservationState, TrendlineAnchor
from lonora_core.user_error import LonoraError

from .health import assess_candles, require_healthy, timeframe_age_seconds
from .watch_lifecycle import candle_close_time

METHODOLOGY = "strict_closed_bar_structure_v1"
_EVIDENCE_LIMIT = 12


@dataclass(frozen=True)
class _Pivot:
    side: Literal["high", "low"]
    index: int
    anchor: TrendlineAnchor
    available_at: datetime
    observation: Observation


def _hash(value: Any) -> str:
    return hashlib.sha256(
        json.dumps(value, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()


def _source_hash(candles: list[Candle], account_id: str) -> str:
    return _hash(
        {"account_id": account_id, "candles": [bar.model_dump(mode="json") for bar in candles]}
    )


def _observation(
    *,
    category: Literal["candle", "trendline"],
    detector_id: str,
    symbol: str,
    timeframe: str,
    observed_at: datetime,
    state: ObservationState,
    values: dict[str, Any],
) -> Observation:
    payload = {
        "category": category,
        "symbol": symbol,
        "timeframe": timeframe,
        "source": "provided_ohlc",
        "observed_at": observed_at.isoformat(),
        "detector_id": detector_id,
        "detector_version": "1",
        "state": state,
        "values": {"methodology": METHODOLOGY, "execution_authorized": False, **values},
    }
    return Observation.model_validate({"id": _hash(payload), **payload})


def _pivots(
    candles: list[Candle], *, account_id: str, left_bars: int, right_bars: int
) -> list[_Pivot]:
    found: list[_Pivot] = []
    for index in range(left_bars, len(candles) - right_bars):
        current = candles[index]
        window = candles[index - left_bars : index + right_bars + 1]
        others = window[:left_bars] + window[left_bars + 1 :]
        available_at = candle_close_time(candles[index + right_bars].time, current.timeframe)
        sides: list[tuple[Literal["high", "low"], Decimal]] = []
        if all(current.high > other.high for other in others):
            sides.append(("high", current.high))
        if all(current.low < other.low for other in others):
            sides.append(("low", current.low))
        for side, price in sides:
            observation = _observation(
                category="candle",
                detector_id="strict_swing_" + side,
                symbol=current.symbol,
                timeframe=current.timeframe,
                observed_at=available_at,
                state="confirmed",
                values={
                    "kind": "swing_" + side,
                    "time": current.time.isoformat(),
                    "price": str(price),
                    "available_at": available_at.isoformat(),
                    "confirmation_bar_at": candles[index + right_bars].time.isoformat(),
                    "left_bars": left_bars,
                    "right_bars": right_bars,
                    "tie_policy": "strict_unique_extremum",
                    "source_hash": _source_hash(window, account_id),
                    "input_first_at": window[0].time.isoformat(),
                    "input_last_at": window[-1].time.isoformat(),
                },
            )
            found.append(
                _Pivot(
                    side,
                    index,
                    TrendlineAnchor(time=current.time, price=price),
                    available_at,
                    observation,
                )
            )
    return found


def _line(
    left: _Pivot,
    right: _Pivot,
    candles: list[Candle],
    *,
    tolerance: Decimal,
    source_hash: str,
) -> Observation:
    width = Decimal(str((right.anchor.time - left.anchor.time).total_seconds()))
    touches: list[dict[str, Any]] = []
    breaks: list[dict[str, Any]] = []
    level = left.anchor.price
    for bar in candles[left.index :]:
        elapsed = Decimal(str((bar.time - left.anchor.time).total_seconds()))
        level = left.anchor.price + (right.anchor.price - left.anchor.price) * elapsed / width
        extreme = bar.low if left.side == "low" else bar.high
        close_at = candle_close_time(bar.time, bar.timeframe)
        evidence = {
            "time": bar.time.isoformat(),
            "available_at": close_at.isoformat(),
            "level": str(level),
            "close": str(bar.close),
        }
        if abs(extreme - level) <= tolerance:
            touches.append({**evidence, "price": str(extreme)})
        breached = (
            bar.close < level - tolerance if left.side == "low" else bar.close > level + tolerance
        )
        if breached:
            breaks.append({**evidence, "after_line_available": close_at >= right.available_at})
    reasons: list[str] = []
    if breaks:
        reasons.append("closed_price_breach")
    if level <= 0:
        reasons.append("projection_outside_positive_price_domain")
    return _observation(
        category="trendline",
        detector_id="swing_support" if left.side == "low" else "swing_resistance",
        symbol=candles[-1].symbol,
        timeframe=candles[-1].timeframe,
        observed_at=candle_close_time(candles[-1].time, candles[-1].timeframe),
        state="invalidated" if reasons else "confirmed",
        values={
            "role": "support" if left.side == "low" else "resistance",
            "anchors": [left.anchor.model_dump(mode="json"), right.anchor.model_dump(mode="json")],
            "anchor_observation_ids": [left.observation.id, right.observation.id],
            "available_at": right.available_at.isoformat(),
            "evaluation_start_at": left.anchor.time.isoformat(),
            "level": str(level),
            "tolerance": str(tolerance),
            "break_basis": "closed_close_beyond_absolute_price_tolerance",
            "invalidation_reasons": reasons,
            "touch_count": len(touches),
            "touches": touches[-_EVIDENCE_LIMIT:],
            "touches_truncated": len(touches) > _EVIDENCE_LIMIT,
            "break_count": len(breaks),
            "breaks": breaks[-_EVIDENCE_LIMIT:],
            "breaks_truncated": len(breaks) > _EVIDENCE_LIMIT,
            "first_break": breaks[0] if breaks else None,
            "source_hash": source_hash,
            "input_first_at": candles[0].time.isoformat(),
            "input_last_at": candles[-1].time.isoformat(),
        },
    )


def analyze_structure(
    candles: list[Candle],
    *,
    account_id: str,
    symbol: str,
    timeframe: str,
    observed_at: datetime,
    left_bars: int = 2,
    right_bars: int = 2,
    tolerance: Decimal = Decimal(0),
    max_pivots: int = 24,
    max_lines: int = 6,
) -> dict[str, Any]:
    """Describe strict swings and recent alternative lines from supplied evidence.

    Lines are selected by recent right/left anchors, alternating support and
    resistance when available, not by a hidden entry rule or profitability score.
    Historical fit breaches are retained even if price later returns to the line.
    """
    if any(type(value) is not int or not 1 <= value <= 100 for value in (left_bars, right_bars)):
        raise LonoraError("market_structure_windows_invalid")
    if type(max_pivots) is not int or not 1 <= max_pivots <= 100:
        raise LonoraError("market_structure_counts_invalid")
    if type(max_lines) is not int or not 1 <= max_lines <= 24:
        raise LonoraError("market_structure_counts_invalid")
    if type(tolerance) is not Decimal or not tolerance.is_finite() or tolerance < 0:
        raise LonoraError("market_structure_tolerance_invalid")
    if len(candles) > 1000:
        raise LonoraError("market_structure_candle_limit")
    if not account_id or not symbol or len(symbol) > 80:
        raise LonoraError("market_structure_scope_invalid")
    if observed_at.tzinfo is None or observed_at.utcoffset() is None:
        raise LonoraError("market_structure_timestamp_invalid")
    maximum_age = timeframe_age_seconds(timeframe)
    common: dict[str, Any] = dict(
        account_id=account_id,
        symbol=symbol,
        timeframe=timeframe,
        now=observed_at,
        maximum_age_seconds=maximum_age,
    )
    require_healthy(assess_candles(candles, **common))
    if any(bar.time > observed_at for bar in candles):
        raise LonoraError("market_candle_timestamp_future", 409)
    closed = [bar for bar in candles if candle_close_time(bar.time, timeframe) <= observed_at]
    health = assess_candles(closed, **common)
    require_healthy(health)
    source_hash = _source_hash(closed, account_id)
    pivots = _pivots(closed, account_id=account_id, left_bars=left_bars, right_bars=right_bars)
    selected = pivots[-max_pivots:]
    alternatives = [
        sorted(
            combinations([pivot for pivot in selected if pivot.side == side], 2),
            key=lambda pair: (pair[1].anchor.time, pair[0].anchor.time),
            reverse=True,
        )
        for side in ("low", "high")
    ]
    pairs: list[tuple[_Pivot, _Pivot]] = []
    for index in range(max((len(group) for group in alternatives), default=0)):
        for group in alternatives:
            if index < len(group) and len(pairs) < max_lines:
                pairs.append(group[index])
        if len(pairs) == max_lines:
            break
    prices = [price for bar in closed for price in (bar.open, bar.high, bar.low, bar.close)]
    # Preserve small differences between large prices without relying on a
    # process-global Decimal context. Pathological exponents fail explicitly.
    precision = max(
        50,
        max(price.adjusted() for price in prices)
        - min(int(price.as_tuple().exponent) for price in prices)
        + 20,
    )
    if precision > 4096:
        raise LonoraError("market_structure_numeric_range_invalid")
    try:
        with localcontext() as context:
            context.prec = precision
            lines = [
                _line(left, right, closed, tolerance=tolerance, source_hash=source_hash)
                for left, right in pairs
            ]
    except DecimalException:
        raise LonoraError("market_structure_numeric_range_invalid") from None
    limitations = [
        "Supplied OHLC provenance is not independently verified by this pure analyzer.",
        "Broker session continuity and holidays are unknown; windows count supplied bars.",
        "Only strict local extrema and bounded recent alternatives are measured, not every chart pattern.",
        "Confirmed means the declared geometry was observed, not an entry signal or a profitability guarantee.",
    ]
    if len(closed) < left_bars + right_bars + 1:
        limitations.append("Insufficient closed bars for the requested swing windows.")
    return {
        "methodology": METHODOLOGY,
        "symbol": symbol,
        "timeframe": timeframe,
        "observed_at": observed_at.isoformat(),
        "source_hash": source_hash,
        "health": health.model_dump(mode="json"),
        "input": {
            "first_at": candles[0].time.isoformat(),
            "last_at": candles[-1].time.isoformat(),
            "bars": len(candles),
            "closed_first_at": closed[0].time.isoformat(),
            "closed_last_at": closed[-1].time.isoformat(),
            "closed_bars": len(closed),
            "excluded_forming_bars": len(candles) - len(closed),
        },
        "configuration": {
            "left_bars": left_bars,
            "right_bars": right_bars,
            "tie_policy": "strict_unique_extremum",
            "tolerance": str(tolerance),
            "max_pivots": max_pivots,
            "max_lines": max_lines,
            "line_selection": "recent_anchor_pairs_alternating_support_resistance",
        },
        "pivots": [pivot.observation.model_dump(mode="json") for pivot in selected],
        "pivots_truncated": len(pivots) > len(selected),
        "trendlines": [line.model_dump(mode="json") for line in lines],
        "execution_authorized": False,
        "limitations": limitations,
    }
