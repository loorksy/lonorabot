"""A stopped Gateway seen from the API, a separate process that is still running (P1-06).

While no Gateway heartbeat is fresh, the owner gets one honest line in the "needs your
attention" view on web and mobile and, past a grace longer than the stall guard's own
restart, one phone push (VISION 11.4 as amended by Amendment 5). The line goes as soon as
a heartbeat is fresh again. Needs PostgreSQL (LONORA_TASK_TEST_DATABASE_URL): the push
cursor reads the published event order.
"""

import asyncio
import os
from datetime import datetime, timedelta
from typing import Any

import pytest
from lonora_bus.attention import attention_text
from lonora_contracts.attention import ATTENTION_EVENTS
from lonora_contracts.domain import utcnow
from lonora_db.attention import attention_view, withdraw_ended
from lonora_db.client import Database
from lonora_db.schema import AttentionRow, GatewayRow
from lonora_gateway.health import STOPPED_AFTER, tell_owner_if_stopped
from sqlalchemy import select
from test_push_sender import CIPHER, PHONE, FakeExpo, phone, started
from test_task_runtime import task_db as task_db

pytestmark = pytest.mark.skipif(
    not os.environ.get("LONORA_TASK_TEST_DATABASE_URL"),
    reason="needs LONORA_TASK_TEST_DATABASE_URL (a disposable *_test PostgreSQL database)",
)
Fixture = tuple[Database, str, str, str]


async def heartbeat(db: Database, at: datetime, state: str = "running") -> None:
    async with db.sessions() as session, session.begin():
        row = await session.get(GatewayRow, "gw-test")
        if row is None:
            row = GatewayRow(id="gw-test", state=state, liveness={})
            session.add(row)
        row.state, row.heartbeat_at = state, at


async def stopped_items(db: Database, owner_id: str) -> list[AttentionRow]:
    async with db.sessions() as session:
        return list(
            await session.scalars(
                select(AttentionRow).where(
                    AttentionRow.owner_id == owner_id, AttentionRow.code == "gateway_stopped"
                )
            )
        )


async def view(db: Database, owner_id: str) -> list[dict[str, object]]:
    async with db.sessions() as session:
        return [row for row in await attention_view(session, owner_id) if row["code"]]


def test_a_stopped_gateway_is_one_of_the_owner_events() -> None:
    assert ATTENTION_EVENTS["gateway_stopped"] == "background_health"
    assert attention_text("gateway_stopped", "ar") != attention_text("gateway_stopped", "en")


@pytest.mark.asyncio
async def test_a_stale_heartbeat_shows_the_stopped_worker_line_and_a_fresh_one_removes_it(
    task_db: Fixture,
) -> None:
    db, owner_id, *_ = task_db
    now = utcnow()
    expo = FakeExpo(db)
    await heartbeat(db, now - timedelta(minutes=10))
    assert await tell_owner_if_stopped(db, now - timedelta(hours=1), CIPHER, expo)
    rows = await view(db, owner_id)
    assert [(row["kind"], row["code"]) for row in rows] == [
        ("background_health", "gateway_stopped")
    ]
    # The same stop raises no second item.
    assert await tell_owner_if_stopped(db, now - timedelta(hours=1), CIPHER, expo)
    assert len(await stopped_items(db, owner_id)) == 1
    # A fresh heartbeat removes the line at once; the Gateway's own sweep withdraws the item.
    await heartbeat(db, utcnow())
    assert await view(db, owner_id) == []
    assert not await tell_owner_if_stopped(db, now - timedelta(hours=1), CIPHER, expo)
    async with db.sessions() as session, session.begin():
        assert await withdraw_ended(session, owner_id) == 1
    assert [item.status for item in await stopped_items(db, owner_id)] == ["suppressed"]
    # The next stop is a new item.
    await heartbeat(db, utcnow() - timedelta(minutes=10))
    assert await tell_owner_if_stopped(db, now - timedelta(hours=1), CIPHER, expo)
    assert len(await stopped_items(db, owner_id)) == 2


@pytest.mark.asyncio
async def test_a_quick_restart_or_an_api_that_just_started_tells_nobody(task_db: Fixture) -> None:
    db, owner_id, *_ = task_db
    now = utcnow()
    expo = FakeExpo(db)
    # The stall guard restarts a stuck Gateway well inside the grace.
    await heartbeat(db, now - STOPPED_AFTER + timedelta(seconds=30))
    assert not await tell_owner_if_stopped(db, now - timedelta(hours=1), CIPHER, expo)
    # After an update the API starts first: the grace counts from its own start.
    await heartbeat(db, now - timedelta(hours=2), state="stopped")
    assert not await tell_owner_if_stopped(db, now - timedelta(seconds=30), CIPHER, expo)
    assert await stopped_items(db, owner_id) == []
    assert await view(db, owner_id) == []


@pytest.mark.asyncio
async def test_a_cleanly_stopped_or_never_started_gateway_is_a_stopped_worker(
    task_db: Fixture,
) -> None:
    db, owner_id, *_ = task_db
    long_ago = utcnow() - timedelta(hours=1)
    assert await tell_owner_if_stopped(db, long_ago, CIPHER, FakeExpo(db))
    assert len(await stopped_items(db, owner_id)) == 1
    # A fresh row that says it stopped is no running Gateway either.
    await heartbeat(db, utcnow(), state="stopped")
    assert [row["code"] for row in await view(db, owner_id)] == ["gateway_stopped"]


@pytest.mark.asyncio
async def test_the_api_pushes_a_stopped_gateway_once(task_db: Fixture) -> None:
    db, owner_id, *_ = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    expo = FakeExpo(db)
    await started(db, owner_id, expo)
    long_ago = utcnow() - timedelta(hours=1)
    await heartbeat(db, utcnow() - timedelta(minutes=10))
    assert await tell_owner_if_stopped(db, long_ago, CIPHER, expo)
    assert await tell_owner_if_stopped(db, long_ago, CIPHER, expo)
    assert len(expo.sent) == 1
    message = expo.sent[0]
    assert message["body"] == attention_text("gateway_stopped", "ar")
    assert set(message["data"]) == {"thread_id"}
    # While a Gateway runs, the API sends nothing: the Gateway's own push step does.
    await heartbeat(db, utcnow())
    assert not await tell_owner_if_stopped(db, long_ago, CIPHER, expo)
    assert len(expo.sent) == 1


@pytest.mark.asyncio
async def test_a_gateway_that_never_ran_still_reaches_the_phone(task_db: Fixture) -> None:
    db, owner_id, *_ = task_db
    await phone(db, owner_id, PHONE, "ExponentPushToken[phone000000000001]")
    # No Gateway ever placed the push cursor: the API's first pass must not skip the stop.
    expo = FakeExpo(db)
    assert await tell_owner_if_stopped(db, utcnow() - timedelta(hours=1), CIPHER, expo)
    assert [message["body"] for message in expo.sent] == [attention_text("gateway_stopped", "ar")]


@pytest.mark.asyncio
async def test_the_api_starts_the_watch_and_it_outlives_a_failed_pass(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import lonora_api.health as api_health
    from lonora_api.app import create_app
    from lonora_api.env import get_settings

    calls: list[datetime] = []
    passed = asyncio.Event()

    async def told(db: Database, since: datetime, cipher: Any, transport: Any) -> bool:
        calls.append(since)
        if len(calls) == 1:
            raise RuntimeError("database away for a moment")
        passed.set()
        return False

    monkeypatch.setattr(api_health, "WATCH_SECONDS", 0.01)
    monkeypatch.setattr(api_health, "tell_owner_if_stopped", told)
    app = create_app(get_settings().model_copy(update={"chart_renderer_root": None}))
    # The API's lifespan starts the watch; one failed pass does not end it.
    async with app.router.lifespan_context(app):
        await asyncio.wait_for(passed.wait(), timeout=10)
    assert len(calls) >= 2 and len(set(calls)) == 1
