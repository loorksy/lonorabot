"""Actual event bursts stay responsive; quiet subscriptions retain idle backoff."""

from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from lonora_bus import durable_events
from lonora_db.client import Database


@asynccontextmanager
async def session():
    yield None


def event_identity(row: Any) -> Any:
    return row


@pytest.mark.asyncio
async def test_active_delivery_does_not_accumulate_half_second_batches(
    monkeypatch: pytest.MonkeyPatch,
):
    now = 0.0
    pauses: list[float] = []

    async def pause(seconds: float) -> None:
        nonlocal now
        pauses.append(seconds)
        now += seconds

    reader = AsyncMock(side_effect=[[{"cursor": 7}], [], [], [{"cursor": 8}]])
    monkeypatch.setattr(durable_events, "monotonic", lambda: now)
    monkeypatch.setattr(durable_events.asyncio, "sleep", pause)
    monkeypatch.setattr(durable_events, "events_after", reader)
    monkeypatch.setattr(durable_events, "event_data", event_identity)
    db = cast(Database, SimpleNamespace(sessions=session))
    stream = durable_events.stream_events(db, "owner", 6, "thread")
    try:
        assert (await anext(stream))["cursor"] == 7
        assert (await anext(stream))["cursor"] == 8
        assert sum(pauses) < 0.5
        assert [call.args[2] for call in reader.await_args_list] == [6, 7, 7, 7]
        assert all(
            call.args[1] == "owner" and call.args[3] == "thread" for call in reader.await_args_list
        )
    finally:
        await stream.aclose()


@pytest.mark.asyncio
async def test_quiet_subscriptions_back_off_and_a_new_event_renews_delivery(
    monkeypatch: pytest.MonkeyPatch,
):
    now = 0.0
    pauses: list[float] = []
    emitted = False

    async def pause(seconds: float) -> None:
        nonlocal now
        pauses.append(seconds)
        now += seconds

    async def read(*_args: Any) -> list[dict[str, int]]:
        nonlocal emitted
        if now >= 6 and not emitted:
            emitted = True
            return [{"cursor": 1}]
        if emitted and now >= 6.7:
            return [{"cursor": 2}]
        return []

    monkeypatch.setattr(durable_events, "monotonic", lambda: now)
    monkeypatch.setattr(durable_events.asyncio, "sleep", pause)
    monkeypatch.setattr(durable_events, "events_after", read)
    monkeypatch.setattr(durable_events, "event_data", event_identity)
    stream = durable_events.stream_events(
        cast(Database, SimpleNamespace(sessions=session)), "owner"
    )
    try:
        assert (await anext(stream))["cursor"] == 1
        assert pauses[0] < pauses[-1] and pauses[-1] == 0.5
        boundary = len(pauses)
        assert (await anext(stream))["cursor"] == 2
        assert all(delay < 0.5 for delay in pauses[boundary:])
    finally:
        await stream.aclose()
