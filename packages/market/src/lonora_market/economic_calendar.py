import asyncio
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import TYPE_CHECKING, Any, Protocol

from lonora_contracts.market import CalendarEvent
from lonora_core.user_error import LonoraError

if TYPE_CHECKING:
    from lonora_db.client import Database


class CalendarSource(Protocol):
    async def events(self) -> list[CalendarEvent]: ...


def calendar_window(
    events: list[CalendarEvent], start: datetime, end: datetime, currencies: set[str]
) -> list[CalendarEvent]:
    return sorted(
        [
            event
            for event in events
            if start <= event.scheduled_at <= end
            and (not currencies or event.currency in currencies)
        ],
        key=lambda event: event.scheduled_at,
    )


def _default_source(url: str) -> CalendarSource:
    from lonora_adapters.market.economic_calendar import EconomicCalendarAdapter

    return EconomicCalendarAdapter(url)


async def read_calendar(
    db: "Database",
    owner_id: str,
    *,
    source: Callable[[str], CalendarSource] = _default_source,
    timeout_seconds: float = 20,
) -> tuple[list[dict[str, Any]], list[tuple[str, CalendarEvent]]]:
    """Read every enabled owner calendar integration; failures stay per source.

    Returns public source status (never the configured URL) and events tagged
    with the integration ID that a calendar watch can reference.
    """
    from lonora_db.schema import IntegrationRow
    from sqlalchemy import select

    async with db.sessions() as session:
        rows = (
            await session.scalars(
                select(IntegrationRow)
                .where(IntegrationRow.owner_id == owner_id)
                .order_by(IntegrationRow.id)
            )
        ).all()
    configured = [
        row
        for row in rows
        if row.payload.get("type") == "economic_calendar"
        and row.payload.get("enabled")
        and row.payload.get("url")
    ]

    async def fetch(url: str) -> list[CalendarEvent] | str:
        try:
            async with asyncio.timeout(timeout_seconds):
                return await source(url).events()
        except LonoraError as error:
            return error.code
        except TimeoutError:
            return "calendar_source_timeout"

    results = await asyncio.gather(*(fetch(str(row.payload["url"])) for row in configured))
    sources: list[dict[str, Any]] = []
    events: list[tuple[str, CalendarEvent]] = []
    for row, result in zip(configured, results, strict=True):
        status: dict[str, Any] = {"integration_id": row.id, "name": row.payload.get("name")}
        if isinstance(result, str):
            sources.append({**status, "status": "unavailable", "reason": result})
            continue
        # A timestamp without a zone cannot be placed in time; it is reported, never guessed.
        valid = [
            event
            for event in result
            if event.scheduled_at.utcoffset() is not None
            and event.observed_at.utcoffset() is not None
        ]
        sources.append(
            {
                **status,
                "status": "ok",
                "events": len(valid),
                "rejected_without_timezone": len(result) - len(valid),
            }
        )
        events.extend((row.id, event) for event in valid)
    return sources, events


def select_events(
    events: list[tuple[str, CalendarEvent]],
    *,
    now: datetime,
    hours_back: int,
    hours_ahead: int,
    currencies: set[str],
    impacts: set[str],
    limit: int,
) -> tuple[list[dict[str, Any]], int]:
    """Bounded, time-ordered events in the window; returns (page, total matches)."""
    start, end = now - timedelta(hours=hours_back), now + timedelta(hours=hours_ahead)
    matches = sorted(
        (
            (integration_id, event)
            for integration_id, event in events
            if start <= event.scheduled_at <= end
            and (not currencies or event.currency.upper() in currencies)
            and (not impacts or event.impact.casefold() in impacts)
        ),
        key=lambda item: (item[1].scheduled_at, item[1].id),
    )
    page = [
        {
            "id": event.id,
            "name": event.name,
            "currency": event.currency,
            "impact": event.impact,
            "scheduled_at": event.scheduled_at.isoformat(),
            "minutes_from_now": int((event.scheduled_at - now).total_seconds() // 60),
            "status": "upcoming"
            if event.scheduled_at > now
            else "released"
            if event.actual is not None
            else "due_without_actual",
            "actual": event.actual,
            "forecast": event.forecast,
            "source": event.source,
            "observed_at": event.observed_at.isoformat(),
            "integration_id": integration_id,
        }
        for integration_id, event in matches[:limit]
    ]
    return page, len(matches)
