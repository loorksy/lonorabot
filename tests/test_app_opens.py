"""App opens (VISION 11.1, 8.1): the owner's first open of each local date, with the
device's zone, and the morning brief time learned from them. Runs on in-memory SQLite, or
on LONORA_TASK_TEST_DATABASE_URL."""

from collections.abc import AsyncGenerator
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

import httpx
import pytest
import pytest_asyncio
from fastapi import FastAPI
from lonora_api.errors import install_errors
from lonora_api.routes import app_opens
from lonora_auth.sessions import issue_session
from lonora_contracts.app_opens import AppOpen
from lonora_db.app_opens import record_open, recorded_opens
from lonora_db.client import Database
from lonora_db.schema import AppOpenRow, MorningBriefRow, OwnerRow
from lonora_trading.morning_brief import (
    DEFAULT_MINUTE,
    brief_tick,
    learned_minute,
    moved_minute,
    owner_zone,
)
from sqlalchemy import select
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]


def test_the_time_is_07_00_until_three_days_of_opens_then_the_median_less_15_minutes() -> None:
    assert learned_minute([]) is None
    assert learned_minute([400, 410]) is None
    assert learned_minute([400, 410, 430]) == 410 - 15


def test_the_time_moves_at_most_one_hour_per_day() -> None:
    assert moved_minute(DEFAULT_MINUTE, 300) == DEFAULT_MINUTE - 60
    assert moved_minute(DEFAULT_MINUTE, 560) == DEFAULT_MINUTE + 60
    assert moved_minute(DEFAULT_MINUTE, 430) == 430


def test_the_owner_zone_is_reach_me_then_the_latest_device_then_utc() -> None:
    assert owner_zone({"timezone": "Asia/Riyadh"}, "Europe/Paris").key == "Asia/Riyadh"
    assert owner_zone({}, "Europe/Paris").key == "Europe/Paris"
    assert owner_zone({"timezone": "Not/AZone"}, None).key == "UTC"
    assert owner_zone({}, None).key == "UTC"


@pytest.mark.asyncio
async def test_the_first_open_of_each_device_date_is_kept(task_db: Fixture) -> None:
    db, owner, _agent, _thread = task_db
    riyadh = AppOpen(timezone="Asia/Riyadh")
    # 23:30 UTC on the 11th is 02:30 on the 12th in Riyadh.
    times = [
        datetime(2026, 11, 11, 23, 30, tzinfo=UTC),
        datetime(2026, 11, 12, 5, 0, tzinfo=UTC),
        datetime(2026, 11, 13, 4, 0, tzinfo=UTC),
    ]
    async with db.sessions() as session, session.begin():
        assert [await record_open(session, owner, riyadh, at) for at in times] == [
            True,
            False,
            True,
        ]
    async with db.sessions() as session:
        rows = await recorded_opens(session, owner)
    assert [(row.local_date, row.timezone) for row in rows] == [
        ("2026-11-12", "Asia/Riyadh"),
        ("2026-11-13", "Asia/Riyadh"),
    ]


@pytest_asyncio.fixture
async def api(task_db: Fixture) -> AsyncGenerator[tuple[FastAPI, Database, str]]:
    db, owner_id, _, _ = task_db
    app = FastAPI()
    app.state.runtime = SimpleNamespace(db=db)
    install_errors(app)
    app.include_router(app_opens.router, prefix="/api")
    yield app, db, owner_id


def client(app: FastAPI, token: str | None) -> httpx.AsyncClient:
    headers = {"Authorization": "Bearer " + token} if token else {}
    return httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="https://t", headers=headers
    )


@pytest.mark.asyncio
async def test_only_the_signed_in_owner_records_an_open_with_a_real_zone(api: Any) -> None:
    app, db, owner_id = api
    async with client(app, None) as anonymous:
        assert (await anonymous.post("/api/app-opens", json={"timezone": "UTC"})).status_code == 401
    async with db.sessions() as session, session.begin():
        owner = await session.get(OwnerRow, owner_id)
        assert owner
        token, _ = await issue_session(session, owner, 3600)
    async with client(app, token) as phone:
        bad = await phone.post("/api/app-opens", json={"timezone": "Mars/Base"})
        assert bad.status_code == 422
        first = await phone.post("/api/app-opens", json={"timezone": "Asia/Tokyo"})
        again = await phone.post("/api/app-opens", json={"timezone": "Asia/Tokyo"})
    assert first.json() == {"recorded": True} and again.json() == {"recorded": False}
    async with db.sessions() as session:
        assert len(list(await session.scalars(select(AppOpenRow)))) == 1


async def opened(db: Database, owner: str, rows: list[tuple[str, datetime]]) -> None:
    async with db.sessions() as session, session.begin():
        for zone, at in rows:
            await record_open(session, owner, AppOpen(timezone=zone), at)


async def planned(db: Database, owner: str) -> int:
    async with db.sessions() as session:
        record = await session.get(MorningBriefRow, owner)
        assert record is not None
        return record.brief_minute


@pytest.mark.asyncio
async def test_the_brief_time_is_learned_from_the_opens_in_the_device_zone(
    task_db: Fixture,
) -> None:
    db, owner, _agent, _thread = task_db
    # Two days of opens at 05:00 Riyadh: fewer than 3, so 07:00, and in the device zone.
    day = datetime(2026, 11, 10, 2, 0, tzinfo=UTC)
    await opened(db, owner, [("Asia/Riyadh", day), ("Asia/Riyadh", day + timedelta(days=1))])
    # 06:59 Riyadh on the 12th (03:59 UTC): not yet; 07:00 is the time.
    assert await brief_tick(db, owner, now=datetime(2026, 11, 12, 3, 59, tzinfo=UTC)) is None
    assert await planned(db, owner) == DEFAULT_MINUTE
    # A third day of opens at 05:00: the target is 04:45; the time moves one hour a day.
    await opened(db, owner, [("Asia/Riyadh", day + timedelta(days=2))])
    async with db.sessions() as session, session.begin():
        record = await session.get(MorningBriefRow, owner)
        assert record is not None
        record.last_local_date = "2026-11-13"
    await brief_tick(db, owner, now=datetime(2026, 11, 13, 1, 0, tzinfo=UTC))
    assert await planned(db, owner) == DEFAULT_MINUTE - 60
    await brief_tick(db, owner, now=datetime(2026, 11, 14, 1, 0, tzinfo=UTC))
    assert await planned(db, owner) == DEFAULT_MINUTE - 120
    # Planned once per local date: later ticks that day leave it.
    await brief_tick(db, owner, now=datetime(2026, 11, 14, 1, 30, tzinfo=UTC))
    assert await planned(db, owner) == DEFAULT_MINUTE - 120
    await brief_tick(db, owner, now=datetime(2026, 11, 15, 1, 0, tzinfo=UTC))
    assert await planned(db, owner) == 4 * 60 + 45


@pytest.mark.asyncio
async def test_a_trip_keeps_the_habit_of_the_local_clock(task_db: Fixture) -> None:
    db, owner, _agent, _thread = task_db
    # Ten mornings at 07:00 in New York, then one at 07:00 in London.
    new_york = datetime(2026, 11, 1, 12, 0, tzinfo=UTC)
    await opened(db, owner, [("America/New_York", new_york + timedelta(days=n)) for n in range(10)])
    await opened(db, owner, [("Europe/London", datetime(2026, 11, 12, 7, 0, tzinfo=UTC))])
    async with db.sessions() as session, session.begin():
        session.add(MorningBriefRow(owner_id=owner, brief_minute=6 * 60 + 45, baseline={}))
    await brief_tick(db, owner, now=datetime(2026, 11, 13, 1, 0, tzinfo=UTC))
    # The owner's zone is now London's, and the habit is still 07:00, so 06:45.
    assert await planned(db, owner) == 6 * 60 + 45
