"""Deterministic integrity checks. Policies come from the consumer, never from prices.

A source timestamp and a receive timestamp answer different questions. Re-reading a
stale cache must never make its source observation fresh. Candle continuity is only
asserted when the caller knows the expected cadence (including market sessions).
"""

from datetime import datetime
from math import isfinite
from typing import TYPE_CHECKING, Any, Literal

if TYPE_CHECKING:
    from lonora_db.client import Database

from lonora_contracts.account import AccountState
from lonora_contracts.market import Candle, Quote
from lonora_contracts.market_health import HealthSnapshot, HealthState
from lonora_core.user_error import LonoraError


def _aware(value: datetime) -> bool:
    return value.tzinfo is not None and value.utcoffset() is not None


def _snapshot(
    state: HealthState,
    reason: str,
    *,
    resource: Literal["quote", "candles", "account", "broker", "watch"],
    account_id: str,
    now: datetime,
    symbol: str | None = None,
    timeframe: str | None = None,
    last_good_at: datetime | None = None,
    measurements: dict[str, Any] | None = None,
) -> HealthSnapshot:
    return HealthSnapshot(
        state=state,
        reason_code=reason,
        resource=resource,
        account_id=account_id,
        symbol=symbol,
        timeframe=timeframe,
        observed_at=now,
        last_good_at=now if state == "healthy" else last_good_at,
        measurements=measurements or {},
    )


def _freshness(
    source_at: datetime,
    now: datetime,
    maximum_age_seconds: float,
    received_at: datetime | None,
    maximum_receive_age_seconds: float | None,
) -> tuple[HealthState, str, dict[str, Any]]:
    if maximum_age_seconds <= 0 or not isfinite(maximum_age_seconds):
        raise ValueError("invalid_health_freshness_policy")
    if not _aware(now):
        raise ValueError("health_now_requires_timezone")
    if not _aware(source_at):
        return "degraded", "timestamp_invalid", {}
    age = (now - source_at).total_seconds()
    measurements: dict[str, Any] = {
        "source_at": source_at.isoformat(),
        "age_seconds": age,
        "maximum_age_seconds": maximum_age_seconds,
    }
    # A small explicit transport clock-skew allowance; future data is not fresh.
    if age < -5:
        return "degraded", "timestamp_future", measurements
    if received_at is not None:
        if not _aware(received_at):
            return "degraded", "receive_timestamp_invalid", measurements
        received_age = (now - received_at).total_seconds()
        measurements.update(received_at=received_at.isoformat(), receive_age_seconds=received_age)
        if received_age < -5:
            return "degraded", "receive_timestamp_future", measurements
        if maximum_receive_age_seconds is not None:
            if maximum_receive_age_seconds <= 0 or not isfinite(maximum_receive_age_seconds):
                raise ValueError("invalid_health_receive_policy")
            if received_age > maximum_receive_age_seconds:
                return "stale", "receive_stale", measurements
    if age > maximum_age_seconds:
        return "stale", "stale", measurements
    return "healthy", "healthy", measurements


def assess_quote(
    quote: Quote | None,
    *,
    account_id: str,
    symbol: str,
    now: datetime,
    maximum_age_seconds: float,
    received_at: datetime | None = None,
    maximum_receive_age_seconds: float | None = None,
    last_good_at: datetime | None = None,
) -> HealthSnapshot:
    common: dict[str, Any] = dict(
        resource="quote", account_id=account_id, symbol=symbol, now=now, last_good_at=last_good_at
    )
    if quote is None:
        return _snapshot("unavailable", "market_quote_unavailable", **common)
    if quote.symbol != symbol:
        return _snapshot("degraded", "broker_symbol_mismatch", **common)
    if (
        not quote.bid.is_finite()
        or not quote.ask.is_finite()
        or quote.bid <= 0
        or quote.ask < quote.bid
    ):
        return _snapshot("degraded", "market_quote_invalid", **common)
    state, reason, measurements = _freshness(
        quote.observed_at, now, maximum_age_seconds, received_at, maximum_receive_age_seconds
    )
    measurements.update(bid=str(quote.bid), ask=str(quote.ask), spread=str(quote.ask - quote.bid))
    return _snapshot(state, "market_quote_" + reason, measurements=measurements, **common)


def assess_account(
    account: AccountState | None,
    *,
    account_id: str,
    now: datetime,
    maximum_age_seconds: float,
    received_at: datetime | None = None,
    maximum_receive_age_seconds: float | None = None,
    last_good_at: datetime | None = None,
) -> HealthSnapshot:
    common: dict[str, Any] = dict(
        resource="account", account_id=account_id, now=now, last_good_at=last_good_at
    )
    if account is None:
        return _snapshot("unavailable", "broker_account_unavailable", **common)
    if any(
        not value.is_finite()
        for value in (account.balance, account.equity, account.margin, account.free_margin)
    ):
        return _snapshot("degraded", "broker_account_invalid", **common)
    state, reason, measurements = _freshness(
        account.observed_at, now, maximum_age_seconds, received_at, maximum_receive_age_seconds
    )
    return _snapshot(state, "broker_account_" + reason, measurements=measurements, **common)


def assess_candles(
    candles: list[Candle],
    *,
    account_id: str,
    symbol: str,
    timeframe: str,
    now: datetime,
    maximum_age_seconds: float,
    received_at: datetime | None = None,
    maximum_receive_age_seconds: float | None = None,
    expected_interval_seconds: float | None = None,
    last_good_at: datetime | None = None,
) -> HealthSnapshot:
    common: dict[str, Any] = dict(
        resource="candles",
        account_id=account_id,
        symbol=symbol,
        timeframe=timeframe,
        now=now,
        last_good_at=last_good_at,
    )
    if not candles:
        return _snapshot("unavailable", "market_candles_unavailable", **common)
    if any(c.symbol != symbol or c.timeframe != timeframe for c in candles):
        return _snapshot("degraded", "mixed_candle_series", **common)
    if any(not _aware(c.time) for c in candles):
        return _snapshot("degraded", "market_candle_timestamp_invalid", **common)
    times = [c.time for c in candles]
    if len(set(times)) != len(times):
        return _snapshot("degraded", "duplicate_candle_timestamp", **common)
    if times != sorted(times):
        return _snapshot("degraded", "market_candle_out_of_order", **common)
    for candle in candles:
        prices = (candle.open, candle.high, candle.low, candle.close)
        if (
            any(not price.is_finite() or price <= 0 for price in prices)
            or candle.low > min(candle.open, candle.close)
            or candle.high < max(candle.open, candle.close)
            or candle.low > candle.high
        ):
            return _snapshot("degraded", "market_candle_invalid", **common)
    state, reason, measurements = _freshness(
        times[-1], now, maximum_age_seconds, received_at, maximum_receive_age_seconds
    )
    measurements.update(bar_count=len(candles), continuity="unknown")
    if expected_interval_seconds is not None:
        if expected_interval_seconds <= 0 or not isfinite(expected_interval_seconds):
            raise ValueError("invalid_candle_cadence")
        gaps = [
            (right - left).total_seconds() for left, right in zip(times, times[1:], strict=False)
        ]
        measurements.update(
            continuity="checked", expected_interval_seconds=expected_interval_seconds
        )
        if any(gap > expected_interval_seconds * 1.5 for gap in gaps):
            return _snapshot("degraded", "market_candle_gap", measurements=measurements, **common)
    return _snapshot(state, "market_candles_" + reason, measurements=measurements, **common)


def timeframe_age_seconds(timeframe: str) -> float:
    """Two bars allow a just-closed-bar source; monthly bars use calendar bounds.

    This is a freshness horizon, NOT a promise of session-continuous candles.
    """
    from lonora_core.chart_controller import validate_timeframe

    validate_timeframe(timeframe)
    if timeframe == "1mn":
        return 2 * 31 * 86400
    amount, unit = int(timeframe[:-1]), timeframe[-1]
    return float(amount * {"m": 60, "h": 3600, "d": 86400, "w": 604800}[unit] * 2)


def require_healthy(snapshot: HealthSnapshot) -> None:
    if not snapshot.healthy:
        raise LonoraError(snapshot.reason_code, 409)


async def record_market_health(
    db: "Database",
    owner_id: str,
    health: HealthSnapshot,
    *,
    expected_version: int | None = None,
    stream_owner: str | None = None,
) -> None:
    """Bounded latest resource state; full meaningful history uses existing events."""
    from lonora_db.broker_sessions import BrokerSessionRepository
    from lonora_db.events import emit

    key = ":".join((health.resource, health.symbol or "", health.timeframe or ""))
    async with db.sessions() as session, session.begin():
        connection = await BrokerSessionRepository().get(
            session, owner_id, health.account_id, lock=True
        )
        if expected_version is not None and connection.version != expected_version:
            return
        if stream_owner and (
            connection.state.get("market_stream_owner") != stream_owner
            or not connection.state.get("market_stream_until")
            or datetime.fromisoformat(connection.state["market_stream_until"]) <= health.observed_at
        ):
            return
        resources = dict(connection.state.get("market_health", {}))
        previous = resources.pop(key, {})
        if not health.healthy and health.last_good_at is None and previous.get("last_good_at"):
            health = health.model_copy(
                update={"last_good_at": datetime.fromisoformat(previous["last_good_at"])}
            )
        resources[key] = health.model_dump(mode="json")
        connection.state = {
            **connection.state,
            "market_health": dict(list(resources.items())[-64:]),
        }
        if (previous.get("state"), previous.get("reason_code")) != (
            health.state,
            health.reason_code,
        ) and (previous or not health.healthy):
            emit(
                session,
                owner_id,
                "market_data.recovered" if health.healthy else "market_data." + health.state,
                payload={
                    "connection_id": health.account_id,
                    "health": health.model_dump(mode="json"),
                },
            )
