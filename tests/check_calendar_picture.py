"""The calendar part of the account picture (mandate 5.4, third bullet).

Only an owner-configured source; the gateway step caches its events with impact
normalised to low/medium/high; the picture carries the high-impact events of the
next 24 hours for the picture's currencies, or "calendar not connected".
"""

import asyncio
from datetime import timedelta
from typing import Any

from check_account_picture import Book, picture_of, position
from check_streaming import Fixture
from lonora_agent.context.picture import account_picture
from lonora_contracts.domain import utcnow
from lonora_contracts.market import CalendarEvent
from lonora_core.user_error import LonoraError
from lonora_db.schema import BrokerSessionRow, EconomicCalendarRow, IntegrationRow
from lonora_market.economic_calendar import cache_calendar, normalized_impact
from lonora_trading.picture import CURRENCIES_KEY
from sqlalchemy import select


class Source:
    def __init__(self, events: list[CalendarEvent] | None) -> None:
        self.value = events

    async def events(self) -> list[CalendarEvent]:
        if self.value is None:
            raise LonoraError("calendar_source_unavailable", 502)
        return self.value


def event(name: str, currency: str, impact: str, hours: float) -> CalendarEvent:
    now = utcnow()
    return CalendarEvent(
        id=name,
        name=name,
        currency=currency,
        impact=impact,
        scheduled_at=now + timedelta(hours=hours),
        observed_at=now,
        source="fixture",
    )


async def calendar(f: Fixture, agent_id: str) -> Any:
    async with f.runtime.db.sessions() as session:
        return picture_of(await account_picture(session, f.owner, agent_id))["calendar"]


async def main() -> None:
    assert [normalized_impact(word) for word in ("High", " 3 ", "Medium", "low", "??")] == [
        "high",
        "high",
        "medium",
        "low",
        None,
    ]
    f = await Fixture().open()
    try:
        account = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": "picture-source", "enabled": True},
            )
        )["id"]
        agent = await f.agent("Euro book")
        book = Book(f, account)
        await book.opened(agent["id"], position("eur-1", "EURUSD", "buy", "1.0", "0"))
        await book.reconcile()
        async with f.runtime.db.sessions() as session, session.begin():
            row = await session.get(BrokerSessionRow, account, with_for_update=True)
            assert row
            row.state = {**row.state, CURRENCIES_KEY: {"EURUSD": ["EUR", "USD"]}}
        assert await calendar(f, agent["id"]) == "calendar not connected"
        print("PASS without an owner source the picture says calendar not connected")

        async with f.runtime.db.sessions() as session, session.begin():
            integration = IntegrationRow(
                owner_id=f.owner,
                payload={
                    "type": "economic_calendar",
                    "enabled": True,
                    "url": "https://calendar.invalid/feed",
                    "name": "Owner feed",
                },
            )
            session.add(integration)
        listed = await calendar(f, agent["id"])
        assert (
            listed["sources"] == [{"status": "not_read_yet"}] and not listed["high_impact_next_24h"]
        ), listed
        feed = [
            event("ECB rate decision", "EUR", "High", 3),
            event("German retail sales", "EUR", "Low", 2),
            event("US payrolls", "USD", "3", 1),
            event("BoJ decision", "JPY", "high", 2),  # not a held currency
            event("US CPI", "USD", "high", 30),  # beyond 24 hours
            event("FOMC minutes", "USD", "high", -2),  # already past
        ]
        assert await cache_calendar(f.runtime.db, f.owner, source=lambda _: Source(feed)) == 6
        listed = await calendar(f, agent["id"])
        names = [item["name"] for item in listed["high_impact_next_24h"]]
        assert names == ["US payrolls", "ECB rate decision"], listed
        assert listed["sources"][0]["status"] == "ok" and listed["sources"][0]["fetched_at"]
        print("PASS only high-impact events of the next 24 hours for held currencies appear")

        # A source that fails keeps its last events and says so.
        assert await cache_calendar(f.runtime.db, f.owner, source=lambda _: Source(None)) == 0
        listed = await calendar(f, agent["id"])
        assert listed["sources"][0]["status"] == "unavailable", listed
        assert [item["name"] for item in listed["high_impact_next_24h"]] == names
        print("PASS a failing source keeps its cached events and reports unavailable")

        # A source the owner removed leaves the cache and the picture.
        async with f.runtime.db.sessions() as session, session.begin():
            saved = await session.get(IntegrationRow, integration.id)
            assert saved
            saved.payload = {**saved.payload, "enabled": False}
        await cache_calendar(f.runtime.db, f.owner, source=lambda _: Source(feed))
        async with f.runtime.db.sessions() as session:
            assert not list(await session.scalars(select(EconomicCalendarRow)))
        assert await calendar(f, agent["id"]) == "calendar not connected"
        print("PASS a disabled source leaves the cache")
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
