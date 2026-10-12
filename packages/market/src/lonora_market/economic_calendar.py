from datetime import datetime

from lonora_contracts.market import CalendarEvent


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
