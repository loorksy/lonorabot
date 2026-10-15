"""Pure, versioned observations over real prices/OHLC; reusable for live and replay."""

import hashlib
import json
from datetime import datetime
from decimal import Decimal
from typing import Any

from lonora_contracts.market import Candle, Quote
from lonora_contracts.market_intelligence import DetectorDefinition, Observation, ObservationState


def detector_inputs(definition: DetectorDefinition) -> set[str]:
    if definition.children:
        return set[str]().union(*(detector_inputs(child) for child in definition.children))
    return {"candles" if definition.kind == "candle" else "quote"}


def _observation(
    definition: DetectorDefinition,
    symbol: str,
    timeframe: str,
    source: str,
    observed_at: datetime,
    state: ObservationState,
    values: dict[str, Any],
) -> Observation:
    data = dict(
        category="composite" if definition.children else definition.kind,
        symbol=symbol,
        timeframe=timeframe,
        source=source,
        observed_at=observed_at.isoformat(),
        detector_id=definition.id,
        detector_version="1",
        state=state,
        values=values,
    )
    identity = hashlib.sha256(
        json.dumps(data, sort_keys=True, separators=(",", ":")).encode()
    ).hexdigest()
    return Observation.model_validate({"id": identity, **data})


def evaluate_detector(
    definition: DetectorDefinition,
    *,
    symbol: str,
    timeframe: str,
    quote: Quote | None,
    candles: list[Candle],
    observed_at: datetime,
    previous: Observation | None = None,
) -> Observation:
    """Health must be checked by the caller. Insufficient inputs remain pending.

    Tolerances are explicit absolute-price distances, never a universal pip value.
    Detector observations are facts with provenance; a confirmation is not BUY/SELL.
    """
    if definition.children:
        previous_children: dict[str, Observation] = {
            child["detector_id"]: Observation.model_validate(child)
            for child in list[dict[str, Any]](
                previous.values.get("children", []) if previous else []
            )
        }
        children = [
            evaluate_detector(
                child,
                symbol=symbol,
                timeframe=timeframe,
                quote=quote,
                candles=candles,
                observed_at=observed_at,
                previous=previous_children.get(child.id),
            )
            for child in definition.children
        ]
        matched = [child.state == "confirmed" for child in children]
        if definition.kind == "all":
            confirmed = all(matched)
            developing = any(matched) or any(child.state == "forming" for child in children)
        elif definition.kind == "any":
            confirmed = any(matched)
            developing = any(child.state == "forming" for child in children)
        else:
            # NOT must never turn missing evidence into confirmation.
            confirmed = children[0].values.get("matched") is False
            developing = children[0].state in {"pending", "forming"}
        state: ObservationState = (
            "confirmed"
            if confirmed
            else "forming"
            if developing
            else "invalidated"
            if previous and previous.state == "confirmed"
            else "pending"
        )
        return _observation(
            definition,
            symbol,
            timeframe,
            "composite",
            # Composite evidence cannot renew an old required component merely
            # because another input arrived later. ANY needs only one proof.
            max(child.observed_at for child in children if child.state == "confirmed")
            if definition.kind == "any" and confirmed
            else min(child.observed_at for child in children),
            state,
            {
                "operator": definition.kind,
                "matched": confirmed,
                "children": [child.model_dump(mode="json") for child in children],
            },
        )
    if definition.kind == "candle":
        return _candle(definition, symbol, timeframe, candles, observed_at, previous)
    if quote is None:
        return _observation(
            definition,
            symbol,
            timeframe,
            "unavailable",
            observed_at,
            "pending",
            {"missing": ["quote"]},
        )
    if definition.kind == "zone":
        assert definition.lower is not None and definition.upper is not None
        matched = definition.lower <= quote.bid <= definition.upper
        distance = min(abs(quote.bid - definition.lower), abs(quote.bid - definition.upper))
        if previous and previous.state == "confirmed" and definition.exit_tolerance is not None:
            matched = (
                definition.lower - definition.exit_tolerance
                <= quote.bid
                <= definition.upper + definition.exit_tolerance
            )
        values = {
            "bid": str(quote.bid),
            "lower": str(definition.lower),
            "upper": str(definition.upper),
            "distance": str(distance),
        }
    else:
        level = definition.level
        if definition.kind == "trendline":
            left, right = definition.anchors
            elapsed = Decimal(str((quote.observed_at - left.time).total_seconds()))
            width = Decimal(str((right.time - left.time).total_seconds()))
            level = left.price + (right.price - left.price) * elapsed / width
        assert level is not None
        distance = abs(quote.bid - level)
        tolerance = definition.tolerance
        hold = definition.exit_tolerance if definition.exit_tolerance is not None else tolerance
        prior_confirmed = previous is not None and previous.state == "confirmed"
        matched = (
            (quote.bid >= level - hold if prior_confirmed else quote.bid > level + tolerance)
            if definition.relation == "above"
            else (quote.bid <= level + hold if prior_confirmed else quote.bid < level - tolerance)
            if definition.relation == "below"
            else distance <= (hold if prior_confirmed else tolerance)
        )
        values: dict[str, Any] = {
            "bid": str(quote.bid),
            "level": str(level),
            "distance": str(distance),
            "relation": definition.relation,
        }
        if definition.kind == "trendline":
            values["anchors"] = [anchor.model_dump(mode="json") for anchor in definition.anchors]
    state = (
        "confirmed"
        if matched
        else "forming"
        if distance <= definition.tolerance
        else "invalidated"
        if previous and previous.state == "confirmed"
        else "pending"
    )
    return _observation(
        definition,
        symbol,
        timeframe,
        quote.source,
        quote.observed_at,
        state,
        {
            **values,
            "matched": matched,
            "tolerance": str(definition.tolerance),
            "exit_tolerance": str(definition.exit_tolerance)
            if definition.exit_tolerance is not None
            else None,
        },
    )


def _candle(
    definition: DetectorDefinition,
    symbol: str,
    timeframe: str,
    candles: list[Candle],
    observed_at: datetime,
    previous: Observation | None,
) -> Observation:
    required = 1 if definition.pattern in {"doji", "bullish_pin", "bearish_pin"} else 2
    if len(candles) < required:
        return _observation(
            definition,
            symbol,
            timeframe,
            "broker_ohlc",
            observed_at,
            "pending",
            {"missing": ["candles"], "required_bars": required, "available_bars": len(candles)},
        )
    current = candles[-1]
    body = abs(current.close - current.open)
    extent = current.high - current.low
    upper = current.high - max(current.open, current.close)
    lower = min(current.open, current.close) - current.low
    prior = candles[-2] if len(candles) > 1 else current
    if definition.pattern == "bullish_engulfing":
        matched = (
            prior.close < prior.open
            and current.close > current.open
            and current.open <= prior.close
            and current.close >= prior.open
        )
    elif definition.pattern == "bearish_engulfing":
        matched = (
            prior.close > prior.open
            and current.close < current.open
            and current.open >= prior.close
            and current.close <= prior.open
        )
    elif definition.pattern == "doji":
        matched = extent > 0 and body / extent <= definition.body_ratio
    elif definition.pattern == "inside_bar":
        matched = current.high < prior.high and current.low > prior.low
    elif definition.pattern == "bullish_pin":
        matched = (
            extent > 0
            and lower >= body * 2
            and lower >= upper * 2
            and current.close >= current.open
        )
    else:
        matched = (
            extent > 0
            and upper >= body * 2
            and upper >= lower * 2
            and current.close <= current.open
        )
    state: ObservationState = (
        "confirmed"
        if matched
        else "invalidated"
        if previous and previous.state == "confirmed"
        else "pending"
    )
    from .watch_lifecycle import candle_close_time

    close_at = candle_close_time(current.time, timeframe)
    closed = close_at <= observed_at
    if matched and not closed:
        state = "forming"
    return _observation(
        definition,
        symbol,
        timeframe,
        "broker_ohlc",
        close_at if closed else current.time,
        state,
        {
            "pattern": definition.pattern,
            "matched": matched if closed else None,
            "is_closed": closed,
            "open_time": current.time.isoformat(),
            "close_time": close_at.isoformat(),
            "body": str(body),
            "range": str(extent),
            "upper_wick": str(upper),
            "lower_wick": str(lower),
            "bars": [bar.model_dump(mode="json") for bar in candles[-required:]],
        },
    )
