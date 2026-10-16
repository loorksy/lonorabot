"""Bounded, server-calculated correlations on identical closed-bar intervals.

Never align by array index, carry forward missing prices, bridge session gaps or
use the currently forming bar. Baseline and recent windows do not overlap.
"""

import hashlib
from datetime import datetime, timedelta
from math import fsum, sqrt

from lonora_contracts.market import Candle
from lonora_contracts.relationships import (
    MarketRelationship,
    RelationshipRequest,
    RelationshipSample,
)
from lonora_core.chart_controller import validate_timeframe

from .health import assess_candles, timeframe_age_seconds
from .watch_lifecycle import candle_close_time as bar_end


def relationship_usable(value: MarketRelationship, now: datetime) -> bool:
    return (
        value.available
        and value.state not in {"unavailable", "unreliable"}
        and value.valid_until is not None
        and value.observed_at <= now < value.valid_until
    )


def _returns(
    candles: list[Candle], timeframe: str, now: datetime
) -> dict[tuple[datetime, datetime], float]:
    closed = [bar for bar in candles if bar_end(bar.time, timeframe) <= now]
    result: dict[tuple[datetime, datetime], float] = {}
    for previous, current in zip(closed, closed[1:], strict=False):
        if bar_end(previous.time, timeframe) != current.time:
            continue
        result[bar_end(previous.time, timeframe), bar_end(current.time, timeframe)] = float(
            current.close.ln() - previous.close.ln()
        )
    return result


def pearson(samples: list[RelationshipSample]) -> float | None:
    if len(samples) < 10:
        return None
    left = fsum(item.left_return for item in samples) / len(samples)
    right = fsum(item.right_return for item in samples) / len(samples)
    covariance = fsum((item.left_return - left) * (item.right_return - right) for item in samples)
    variance_left = fsum((item.left_return - left) ** 2 for item in samples)
    variance_right = fsum((item.right_return - right) ** 2 for item in samples)
    if variance_left <= 1e-24 or variance_right <= 1e-24:
        return None
    return max(-1.0, min(1.0, covariance / sqrt(variance_left * variance_right)))


def measure_relationship(
    params: RelationshipRequest,
    series: list[list[Candle]],
    *,
    identifier: str,
    owner_id: str,
    agent_id: str,
    now: datetime,
) -> MarketRelationship:
    validate_timeframe(params.timeframe)
    result = MarketRelationship(
        id=identifier,
        owner_id=owner_id,
        agent_id=agent_id,
        account_id=params.account_id,
        symbols=params.symbols,
        timeframe=params.timeframe,
        window=params.window,
        observed_at=now,
    )
    for symbol, candles in zip(params.symbols, series, strict=True):
        result.health.append(
            assess_candles(
                candles,
                account_id=params.account_id,
                symbol=symbol,
                timeframe=params.timeframe,
                now=now,
                maximum_age_seconds=timeframe_age_seconds(params.timeframe),
            )
        )
        result.source_hashes.append(
            hashlib.sha256("\n".join(bar.model_dump_json() for bar in candles).encode()).hexdigest()
        )
    result.reason_codes = list(dict.fromkeys(h.reason_code for h in result.health if not h.healthy))
    if result.reason_codes:
        return result
    # Only bars used by the metric identify a repeatable closed-bar observation.
    # Price changes in a forming bar cannot become new confirmation evidence.
    result.source_hashes = [
        hashlib.sha256(
            "\n".join(
                bar.model_dump_json()
                for bar in candles
                if bar_end(bar.time, params.timeframe) <= now
            ).encode()
        ).hexdigest()
        for candles in series
    ]
    returns = [_returns(candles, params.timeframe, now) for candles in series]
    aligned = sorted(returns[0].keys() & returns[1].keys())[-params.window * 2 :]
    result.alignment_ratio = len(aligned) / max(1, min(params.window * 2, max(map(len, returns))))
    result.samples = [
        RelationshipSample(
            start=start,
            end=end,
            left_return=returns[0][start, end],
            right_return=returns[1][start, end],
        )
        for start, end in aligned
    ]
    recent, baseline = result.samples[-params.window :], result.samples[: -params.window]
    result.sample_count, result.baseline_count = len(recent), len(baseline)
    result.correlation, result.baseline_correlation = pearson(recent), pearson(baseline)
    if result.correlation is None:
        result.reason_codes = ["relationship_insufficient_variance_or_samples"]
        return result
    result.available = True
    result.state = "unreliable"
    if result.alignment_ratio < 0.8 or len(recent) < params.window:
        result.reason_codes = ["relationship_alignment_insufficient"]
    elif result.baseline_correlation is None or len(baseline) < params.window:
        result.reason_codes = ["relationship_baseline_insufficient"]
    else:
        current, old = result.correlation, result.baseline_correlation
        result.correlation_delta = current - old
        result.state = (
            "inverted"
            if current * old < 0 and min(abs(current), abs(old)) >= 0.35
            else "breaking"
            if abs(old) >= 0.5 and abs(current) < 0.2
            else "weakening"
            if abs(old) - abs(current) >= 0.2
            else "stable"
        )
    if aligned:
        result.valid_until = min(
            bar_end(aligned[-1][1], params.timeframe),
            *(
                candles[-1].time + timedelta(seconds=timeframe_age_seconds(params.timeframe))
                for candles in series
            ),
        )
        if result.valid_until <= now:
            result.state = "unreliable"
            result.reason_codes = list(
                dict.fromkeys(result.reason_codes + ["relationship_aligned_data_stale"])
            )
    return result
