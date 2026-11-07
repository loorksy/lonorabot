"""Session clock across DST boundaries and broker trading hours; pure, no broker or DB."""

from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from lonora_adapters.brokers.normalize import broker_offset_minutes, trading_hours
from lonora_contracts.market import TradingHours, TradingSessionWindow
from lonora_core.user_error import LonoraError
from lonora_market.sessions import broker_trading_state, session_clock


def at(value: str) -> datetime:
    return datetime.fromisoformat(value).replace(tzinfo=UTC)


def session(result: dict[str, Any], name: str) -> dict[str, Any]:
    return next(item for item in result["sessions"] if item["name"] == name)


@pytest.mark.parametrize(
    ("now", "london_open", "new_york_open", "overlap_until", "london_dst", "new_york_dst"),
    [
        # Northern winter: GMT and EST.
        ("2026-01-14T13:30", "2026-01-14T08:00", "2026-01-14T13:00", "2026-01-14T17:00", 0, 0),
        # US DST began 8 March, UK DST only on 29 March: the overlap widens to five hours.
        ("2026-03-18T12:30", "2026-03-18T08:00", "2026-03-18T12:00", "2026-03-18T17:00", 0, 1),
        # Northern summer: BST and EDT.
        ("2026-07-15T12:30", "2026-07-15T07:00", "2026-07-15T12:00", "2026-07-15T16:00", 1, 1),
        # UK DST ended 25 October, US DST only on 1 November.
        ("2026-10-28T12:30", "2026-10-28T08:00", "2026-10-28T12:00", "2026-10-28T17:00", 0, 1),
    ],
)
def test_london_new_york_follow_their_own_dst_rules(
    now: str,
    london_open: str,
    new_york_open: str,
    overlap_until: str,
    london_dst: int,
    new_york_dst: int,
) -> None:
    result = session_clock(at(now))
    london, new_york = session(result, "london"), session(result, "new_york")
    assert result["fx_market"]["state"] == "open"
    assert london["active"] and london["opened_at"] == at(london_open).isoformat()
    assert new_york["active"] and new_york["opened_at"] == at(new_york_open).isoformat()
    assert london["dst"] is bool(london_dst) and new_york["dst"] is bool(new_york_dst)
    assert result["active_sessions"] == ["london", "new_york"]
    assert result["active_overlaps"] == [
        {
            "sessions": ["london", "new_york"],
            "until": at(overlap_until).isoformat(),
            "minutes_remaining": int((at(overlap_until) - at(now)).total_seconds() // 60),
        }
    ]


def test_spring_forward_weekend_moves_new_york_open_by_one_hour() -> None:
    friday = session(session_clock(at("2026-03-06T14:00")), "new_york")
    assert friday["opened_at"] == at("2026-03-06T13:00").isoformat()
    saturday = session_clock(at("2026-03-07T12:00"))
    assert saturday["fx_market"]["state"] == "closed"
    assert saturday["fx_market"]["reason"] == "fx_weekend"
    assert saturday["active_sessions"] == []
    # The FX week reopens Sunday 17:00 New York, already on EDT (21:00 UTC).
    assert saturday["fx_market"]["next_opens_at"] == at("2026-03-08T21:00").isoformat()
    assert session(saturday, "new_york")["next_opens_at"] == at("2026-03-09T12:00").isoformat()


def test_sydney_dst_ends_in_april_and_is_clipped_by_the_fx_week() -> None:
    summer = session(session_clock(at("2026-03-17T00:00")), "sydney")  # AEDT, UTC+11
    assert summer["active"] and summer["opened_at"] == at("2026-03-16T20:00").isoformat()
    assert summer["dst"] is True
    winter = session(session_clock(at("2026-04-14T00:00")), "sydney")  # AEST, UTC+10
    assert winter["active"] and winter["opened_at"] == at("2026-04-13T21:00").isoformat()
    assert winter["dst"] is False
    # Monday 07:00 Sydney (Sunday 20:00 UTC) precedes the FX week open at 22:00 UTC.
    sunday = session_clock(at("2026-11-08T21:00"))
    assert sunday["fx_market"]["state"] == "closed"
    assert session(sunday, "sydney")["next_opens_at"] == at("2026-11-08T22:00").isoformat()
    opened = session_clock(at("2026-11-08T22:00"))
    assert opened["active_sessions"] == ["sydney"]


@pytest.mark.parametrize(
    ("now", "state"),
    [
        ("2026-11-06T21:59", "open"),  # 16:59 EST
        ("2026-11-06T22:00", "closed"),  # 17:00 EST
        ("2026-07-17T20:59", "open"),  # 16:59 EDT
        ("2026-07-17T21:00", "closed"),  # 17:00 EDT
        ("2026-07-19T20:59", "closed"),  # Sunday before the open
        ("2026-07-19T21:00", "open"),
    ],
)
def test_fx_week_boundaries_are_new_york_wall_clock(now: str, state: str) -> None:
    assert session_clock(at(now))["fx_market"]["state"] == state


def test_upcoming_overlaps_and_naive_time_rejected() -> None:
    result = session_clock(at("2026-01-14T05:00"))
    assert result["active_sessions"] == ["tokyo"]
    upcoming = result["next_overlaps"][0]
    assert upcoming["sessions"] == ["tokyo", "london"]
    assert upcoming["starts_at"] == at("2026-01-14T08:00").isoformat()
    assert upcoming["ends_at"] == at("2026-01-14T09:00").isoformat()
    with pytest.raises(LonoraError) as error:
        session_clock(datetime(2026, 1, 14, 5))
    assert error.value.code == "market_session_timestamp_invalid"


def hours(sessions: dict[str, list[tuple[str, str]]], offset: int | None) -> TradingHours:
    return TradingHours.model_validate(
        {
            "symbol": "XAUUSD.r",
            "utc_offset_minutes": offset,
            "trade_sessions": {
                day: [TradingSessionWindow(start=a, end=b) for a, b in windows]
                for day, windows in sessions.items()
            },
            "observed_at": at("2026-01-14T00:00"),
            "source": "fixture",
        }
    )


WEEKDAY_SESSIONS = {
    day: [("01:05:00", "23:55:00")] for day in ("MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY")
} | {"FRIDAY": [("01:05:00", "23:50:00")]}


def test_broker_hours_on_broker_server_clock() -> None:
    gold = hours(WEEKDAY_SESSIONS, 120)  # A GMT+2 broker server.
    noon = broker_trading_state(gold, at("2026-01-14T12:00"))
    assert noon["state"] == "open" and noon["broker_local_time"] == "Wed 14:00"
    assert noon["closes_at"] == at("2026-01-14T21:55").isoformat()
    assert noon["today_sessions_broker_clock"] == "01:05-23:55"
    rollover = broker_trading_state(gold, at("2026-01-14T22:00"))
    assert rollover["state"] == "closed"
    assert rollover["next_opens_at"] == at("2026-01-14T23:05").isoformat()
    weekend = broker_trading_state(gold, at("2026-01-17T10:00"))
    assert weekend["state"] == "closed"
    assert weekend["next_opens_at"] == at("2026-01-18T23:05").isoformat()


def test_broker_hours_overnight_continuous_unknown_and_restricted() -> None:
    overnight = hours({"MONDAY": [("22:00:00", "02:00:00")]}, 0)
    assert broker_trading_state(overnight, at("2026-01-13T01:00"))["state"] == "open"
    assert broker_trading_state(overnight, at("2026-01-13T02:00"))["state"] == "closed"
    continuous = hours(
        {"MONDAY": [("00:00:00", "24:00:00")], "TUESDAY": [("00:00:00", "24:00:00")]}, 0
    )
    midnight = broker_trading_state(continuous, at("2026-01-12T23:59"))
    assert midnight["state"] == "open"
    assert midnight["closes_at"] == at("2026-01-14T00:00").isoformat()
    unknown = broker_trading_state(hours(WEEKDAY_SESSIONS, None), at("2026-01-14T12:00"))
    assert unknown["state"] == "unknown" and unknown["reason"] == "broker_clock_offset_unknown"
    assert unknown["weekly_sessions_broker_clock"]["SATURDAY"] == "none"
    empty = broker_trading_state(hours({}, 0), at("2026-01-14T12:00"))
    assert empty["state"] == "unknown" and empty["reason"] == "broker_sessions_not_reported"
    disabled = hours(WEEKDAY_SESSIONS, 0).model_copy(
        update={"trade_mode": "SYMBOL_TRADE_MODE_CLOSEONLY"}
    )
    assert broker_trading_state(disabled, at("2026-01-14T12:00"))["trade_restriction"] == (
        "close_only"
    )


def test_metaapi_specification_normalization() -> None:
    price = {"time": at("2026-01-14T12:00:01"), "brokerTime": "2026-01-14 14:00:03.120"}
    assert broker_offset_minutes(price) == 120
    assert broker_offset_minutes({"time": at("2026-01-14T12:00")}) is None
    assert broker_offset_minutes(None) is None
    result = trading_hours(
        {
            "symbol": "XAUUSD.r",
            "tradeMode": "SYMBOL_TRADE_MODE_FULL",
            "tradeSessions": {
                "MONDAY": [{"from": "00:05:00.000", "to": "23:59:59.999"}],
                "TUESDAY": [{"from": "01.00.00.000", "to": "12.30.00.000"}],
            },
        },
        price,
        observed_at=at("2026-01-14T12:00"),
    )
    assert result.utc_offset_minutes == 120 and result.offset_source == "quote_broker_time"
    assert result.trade_sessions["MONDAY"][0].end == "24:00:00"
    assert result.trade_sessions["TUESDAY"][0].start == "01:00:00"
    assert result.trade_sessions["SATURDAY"] == []
    with pytest.raises(ValueError):
        trading_hours(
            {"symbol": "X", "tradeSessions": {"MONDAY": [{"from": "25:00", "to": "26:00"}]}},
            None,
            observed_at=at("2026-01-14T12:00"),
        )


def test_far_horizon_is_bounded() -> None:
    result = session_clock(at("2026-12-24T12:00") + timedelta(minutes=1))
    assert all(item["active"] or item["next_opens_at"] is not None for item in result["sessions"])
