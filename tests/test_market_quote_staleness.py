"""A stored healthy quote is only written when a quote arrives. When quotes stop, read
as it is now, it is stale, never still healthy (0.4)."""

from datetime import UTC, datetime, timedelta

from lonora_contracts.market_health import QUOTE_STALE_AFTER, as_of

NOW = datetime(2026, 11, 19, 12, 0, tzinfo=UTC)


def stored(observed: datetime, **extra: object) -> dict[str, object]:
    return {
        "state": "healthy",
        "reason_code": "healthy",
        "observed_at": observed.isoformat(),
        "last_good_at": observed.isoformat(),
        "account_id": "connection",
        "symbol": "XAUUSDm",
        "resource": "quote",
        **extra,
    }


def test_a_quote_that_stopped_reads_stale_with_its_last_good_time() -> None:
    old = stored(datetime(2026, 11, 12, 13, 38, tzinfo=UTC))
    value = as_of(old, NOW)
    assert value["state"] == "stale" and value["reason_code"] == "market_quote_stale"
    assert value["last_good_at"] == old["last_good_at"]


def test_a_fresh_quote_stays_healthy_and_the_bound_is_two_minutes() -> None:
    assert as_of(stored(NOW - timedelta(seconds=30)), NOW)["state"] == "healthy"
    assert QUOTE_STALE_AFTER == timedelta(minutes=2)
    assert as_of(stored(NOW - QUOTE_STALE_AFTER), NOW)["state"] == "stale"


def test_an_unreadable_time_is_not_healthy_and_other_entries_are_untouched() -> None:
    assert as_of(stored(NOW, observed_at="garbage"), NOW)["state"] == "stale"
    naive = stored(NOW.replace(tzinfo=None) - timedelta(seconds=5))
    assert as_of(naive, NOW)["state"] == "healthy"
    unavailable = stored(NOW - timedelta(days=3), state="unavailable", reason_code="x")
    assert as_of(unavailable, NOW) is unavailable
    candles = stored(NOW - timedelta(days=3), resource="candles")
    assert as_of(candles, NOW) is candles
