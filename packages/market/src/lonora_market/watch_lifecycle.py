"""The same deterministic watch transition function is used live and in replay."""

from datetime import datetime, timedelta
from typing import Any

from lonora_contracts.market_watch import Watch


def candle_close_time(opened_at: datetime, timeframe: str) -> datetime:
    if timeframe == "1mn":
        return opened_at.replace(
            year=opened_at.year + (opened_at.month == 12), month=opened_at.month % 12 + 1, day=1
        )
    from .health import timeframe_age_seconds

    return opened_at + timedelta(seconds=timeframe_age_seconds(timeframe) / 2)


def advance_watch(
    config: Watch,
    state: dict[str, Any],
    *,
    matched: bool,
    observation_id: str,
    observed_at: datetime,
    now: datetime,
) -> tuple[dict[str, Any], bool]:
    result = dict(state)
    previous = result.get("lifecycle", "pending")
    if previous == "expired":
        return result, False
    if config.expires_at is not None and now >= config.expires_at:
        return {
            **result,
            "lifecycle": "expired",
            "lifecycle_reason": "watch_expired",
            "lifecycle_updated_at": now.isoformat(),
        }, False
    valid_until = result.get("confirmation_valid_until")
    if previous == "confirmed" and valid_until and now >= datetime.fromisoformat(valid_until):
        return {
            **result,
            "lifecycle": "expired",
            "lifecycle_reason": "watch_confirmation_expired",
            "lifecycle_updated_at": now.isoformat(),
            "candidate_count": 0,
            "candidate_since": None,
        }, False
    previous_source = result.get("lifecycle_source_at")
    if observed_at > now or (
        previous_source and observed_at < datetime.fromisoformat(previous_source)
    ):
        # Replayed/out-of-order evidence cannot replace newer durable state.
        # Future evidence cannot make a confirmation actionable before its time.
        return result, False
    if not matched:
        result.update(
            lifecycle="invalidated" if previous == "confirmed" else "pending",
            candidate_count=0,
            candidate_since=None,
        )
        result.pop("confirmation_valid_until", None)
    else:
        distinct = result.get("lifecycle_observation_id") != observation_id and (
            not previous_source or observed_at >= datetime.fromisoformat(previous_source)
        )
        count = int(result.get("candidate_count", 0)) + int(distinct)
        since = result.get("candidate_since") or observed_at.isoformat()
        # Queueing delays and repeated polling do not satisfy debounce.
        elapsed = (observed_at - datetime.fromisoformat(since)).total_seconds()
        confirmed = count >= config.required_observations and elapsed >= config.debounce_seconds
        result.update(
            lifecycle="confirmed" if confirmed else "forming",
            candidate_count=count,
            candidate_since=since,
        )
        if confirmed and config.confirmation_ttl_seconds is not None and previous != "confirmed":
            result["confirmation_valid_until"] = (
                observed_at + timedelta(seconds=config.confirmation_ttl_seconds)
            ).isoformat()
        # An already stale confirmation is never actionable even on first observation.
        if (
            confirmed
            and result.get("confirmation_valid_until")
            and datetime.fromisoformat(result["confirmation_valid_until"]) <= now
        ):
            result.update(lifecycle="expired", lifecycle_reason="watch_confirmation_expired")
    result["lifecycle_observation_id"] = observation_id
    result["lifecycle_source_at"] = observed_at.isoformat()
    if result["lifecycle"] != previous:
        result["lifecycle_updated_at"] = now.isoformat()
    return result, result["lifecycle"] == "confirmed"
