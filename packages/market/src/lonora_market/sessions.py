"""DST-correct FX session clock from IANA zones: conventions, never exchange guarantees.

Session hours are the widely used local-time conventions for the four FX centres,
evaluated through zoneinfo so each centre's own daylight-saving rules apply on the
actual date. The wholesale FX week is taken as Sunday 17:00 to Friday 17:00 New York
time. Holidays and liquidity are not modelled. Broker-reported trading hours, when
an adapter exposes them, are what decides whether an instrument can trade.
"""

from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lonora_contracts.market import TradingHours, TradingSessionWindow, TradingWeekday
from lonora_core.user_error import LonoraError

METHODOLOGY = "iana_conventional_fx_sessions_v1"
WEEKDAYS: tuple[TradingWeekday, ...] = (
    "MONDAY",
    "TUESDAY",
    "WEDNESDAY",
    "THURSDAY",
    "FRIDAY",
    "SATURDAY",
    "SUNDAY",
)
FX_WEEK_ZONE = "America/New_York"
FX_WEEK_BOUNDARY = time(17)
_HORIZON_DAYS = 9

Interval = tuple[datetime, datetime]


@dataclass(frozen=True)
class SessionDefinition:
    name: str
    zone: str
    opens: time
    closes: time


SESSIONS = (
    SessionDefinition("sydney", "Australia/Sydney", time(7), time(16)),
    SessionDefinition("tokyo", "Asia/Tokyo", time(9), time(18)),
    SessionDefinition("london", "Europe/London", time(8), time(17)),
    SessionDefinition("new_york", "America/New_York", time(8), time(17)),
)


def _zone(name: str) -> ZoneInfo:
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        raise LonoraError("timezone_database_unavailable", 503) from None


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None or value.utcoffset() is None:
        raise LonoraError("market_session_timestamp_invalid", 422)
    return value.astimezone(UTC)


def _days(center: date) -> list[date]:
    return [center + timedelta(days=offset) for offset in range(-2, _HORIZON_DAYS)]


def _merge(intervals: list[Interval]) -> list[Interval]:
    merged: list[Interval] = []
    for start, end in sorted(intervals):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _intersect(left: list[Interval], right: list[Interval]) -> list[Interval]:
    result: list[Interval] = []
    i = j = 0
    while i < len(left) and j < len(right):
        start = max(left[i][0], right[j][0])
        end = min(left[i][1], right[j][1])
        if start < end:
            result.append((start, end))
        if left[i][1] < right[j][1]:
            i += 1
        else:
            j += 1
    return result


def fx_week(now: datetime) -> list[Interval]:
    """Sunday 17:00 to Friday 17:00 New York wall time, around `now`."""
    zone = _zone(FX_WEEK_ZONE)
    local = _utc(now).astimezone(zone).date()
    weeks: list[Interval] = []
    for day in (local + timedelta(days=offset) for offset in range(-8, _HORIZON_DAYS)):
        if day.weekday() != 6:  # Sunday
            continue
        opens = datetime.combine(day, FX_WEEK_BOUNDARY, zone)
        closes = datetime.combine(day + timedelta(days=5), FX_WEEK_BOUNDARY, zone)
        weeks.append((opens.astimezone(UTC), closes.astimezone(UTC)))
    return _merge(weeks)


def session_windows(definition: SessionDefinition, now: datetime) -> list[Interval]:
    """Local Monday-Friday windows, each converted with that date's own UTC offset."""
    zone = _zone(definition.zone)
    local = _utc(now).astimezone(zone).date()
    return _merge(
        [
            (
                datetime.combine(day, definition.opens, zone).astimezone(UTC),
                datetime.combine(day, definition.closes, zone).astimezone(UTC),
            )
            for day in _days(local)
            if day.weekday() < 5
        ]
    )


def _minutes(delta: timedelta) -> int:
    return int(delta.total_seconds() // 60)


def _state(intervals: list[Interval], now: datetime) -> dict[str, Any]:
    current = next((item for item in intervals if item[0] <= now < item[1]), None)
    if current is not None:
        return {
            "active": True,
            "opened_at": current[0].isoformat(),
            "closes_at": current[1].isoformat(),
            "minutes_to_close": _minutes(current[1] - now),
        }
    upcoming = next((item for item in intervals if item[0] > now), None)
    return {
        "active": False,
        "next_opens_at": upcoming[0].isoformat() if upcoming else None,
        "next_closes_at": upcoming[1].isoformat() if upcoming else None,
        "minutes_to_open": _minutes(upcoming[0] - now) if upcoming else None,
    }


def session_clock(now: datetime, *, upcoming_overlaps: int = 3) -> dict[str, Any]:
    """Current FX sessions, overlaps and FX-week state at an explicit aware instant."""
    now = _utc(now)
    week = fx_week(now)
    week_state = _state(week, now)
    effective: dict[str, list[Interval]] = {}
    sessions: list[dict[str, Any]] = []
    for definition in SESSIONS:
        zone = _zone(definition.zone)
        intervals = _intersect(session_windows(definition, now), week)
        effective[definition.name] = intervals
        local = now.astimezone(zone)
        sessions.append(
            {
                "name": definition.name,
                "zone": definition.zone,
                "local_hours": definition.opens.strftime("%H:%M")
                + "-"
                + definition.closes.strftime("%H:%M"),
                "local_time": local.strftime("%a %H:%M"),
                "utc_offset": local.strftime("%z"),
                "dst": bool(local.dst()),
                **_state(intervals, now),
            }
        )
    overlaps: list[tuple[datetime, datetime, list[str]]] = []
    names = [definition.name for definition in SESSIONS]
    for index, left in enumerate(names):
        for right in names[index + 1 :]:
            for start, end in _intersect(effective[left], effective[right]):
                overlaps.append((start, end, [left, right]))
    overlaps.sort(key=lambda item: (item[0], item[2]))
    active_overlaps = [
        {
            "sessions": pair,
            "until": end.isoformat(),
            "minutes_remaining": _minutes(end - now),
        }
        for start, end, pair in overlaps
        if start <= now < end
    ]
    next_overlaps = [
        {
            "sessions": pair,
            "starts_at": start.isoformat(),
            "ends_at": end.isoformat(),
            "minutes_to_start": _minutes(start - now),
        }
        for start, end, pair in overlaps
        if start > now
    ][:upcoming_overlaps]
    return {
        "methodology": METHODOLOGY,
        "observed_at": now.isoformat(),
        "fx_market": {
            "state": "open" if week_state["active"] else "closed",
            "reason": None if week_state["active"] else "fx_weekend",
            "week_hours": "Sunday 17:00 to Friday 17:00 " + FX_WEEK_ZONE,
            **{key: value for key, value in week_state.items() if key != "active"},
        },
        "sessions": sessions,
        "active_sessions": [item["name"] for item in sessions if item["active"]],
        "active_overlaps": active_overlaps,
        "next_overlaps": next_overlaps,
        "limitations": [
            "Session hours are conventional local-time FX centre hours, not exchange or broker schedules.",
            "Public holidays, early closes and liquidity are not modelled.",
        ],
    }


def _clock(value: str) -> timedelta:
    if value == "24:00:00":
        return timedelta(days=1)
    hours, minutes, seconds = (int(part) for part in value.split(":"))
    return timedelta(hours=hours, minutes=minutes, seconds=seconds)


def _broker_intervals(hours: TradingHours, broker_today: date, offset: timedelta) -> list[Interval]:
    intervals: list[Interval] = []
    for day in _days(broker_today):
        windows = hours.trade_sessions.get(WEEKDAYS[day.weekday()], [])
        midnight = datetime.combine(day, time(0), UTC) - offset
        for window in windows:
            start, end = _clock(window.start), _clock(window.end)
            if end <= start:
                end += timedelta(days=1)
            intervals.append((midnight + start, midnight + end))
    return _merge(intervals)


def _compact_windows(windows: list[TradingSessionWindow]) -> str:
    return ", ".join(window.start[:5] + "-" + window.end[:5] for window in windows) or "none"


def broker_trading_state(hours: TradingHours, now: datetime) -> dict[str, Any]:
    """Evaluate broker-reported sessions; an unmeasured broker clock stays unknown."""
    now = _utc(now)
    result: dict[str, Any] = {
        "symbol": hours.symbol,
        "source": hours.source,
        "clock": hours.clock,
        "utc_offset_minutes": hours.utc_offset_minutes,
        "trade_mode": hours.trade_mode,
        "observed_at": hours.observed_at.isoformat(),
    }
    if hours.trade_mode in {"SYMBOL_TRADE_MODE_DISABLED", "SYMBOL_TRADE_MODE_CLOSEONLY"}:
        result["trade_restriction"] = (
            "trading_disabled" if hours.trade_mode == "SYMBOL_TRADE_MODE_DISABLED" else "close_only"
        )
    if not any(hours.trade_sessions.values()):
        return {**result, "state": "unknown", "reason": "broker_sessions_not_reported"}
    if hours.utc_offset_minutes is None:
        return {
            **result,
            "state": "unknown",
            "reason": "broker_clock_offset_unknown",
            "weekly_sessions_broker_clock": {
                day: _compact_windows(hours.trade_sessions.get(day, [])) for day in WEEKDAYS
            },
        }
    offset = timedelta(minutes=hours.utc_offset_minutes)
    broker_now = now + offset
    intervals = _broker_intervals(hours, broker_now.date(), offset)
    state = _state(intervals, now)
    weekday = WEEKDAYS[broker_now.weekday()]
    return {
        **result,
        "state": "open" if state["active"] else "closed",
        "broker_local_time": broker_now.strftime("%a %H:%M"),
        "today_sessions_broker_clock": _compact_windows(hours.trade_sessions.get(weekday, [])),
        **{
            key: value
            for key, value in state.items()
            if key in {"closes_at", "minutes_to_close", "next_opens_at", "minutes_to_open"}
        },
        "limitations": [
            "The broker clock offset was measured now; a broker DST change inside the horizon is not modelled."
        ],
    }
