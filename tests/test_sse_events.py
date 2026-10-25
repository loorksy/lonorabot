"""SSE readiness, privacy-preserving replay and bounded idle authorization."""

import asyncio
import json
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast

import pytest
from lonora_api.routes import events
from lonora_core.user_error import LonoraError
from starlette.requests import Request


class FakeRequest:
    def __init__(self, headers: dict[str, str] | None = None):
        self.headers = headers or {}
        self.cookies = {"lonora_session": "test-session-only"}
        self.disconnected = False

    async def is_disconnected(self) -> bool:
        return self.disconnected


@asynccontextmanager
async def session() -> AsyncGenerator[None, None]:
    yield None


@pytest.mark.parametrize("value", ["-1", "garbage", str(events.MAX_CURSOR + 1)])
def test_invalid_last_event_id_cannot_change_replay(value: str):
    request = cast(Request, FakeRequest({"last-event-id": value}))
    with pytest.raises(LonoraError, match="event_cursor_invalid"):
        events.resume_cursor(request, 7)


def test_last_event_id_never_moves_cursor_backwards():
    request = cast(Request, FakeRequest({"last-event-id": "42"}))
    assert events.resume_cursor(request, 9) == 42
    assert events.resume_cursor(request, 50) == 50


@pytest.mark.asyncio
async def test_sse_ready_precedes_events_and_closes_source(monkeypatch: pytest.MonkeyPatch):
    request = FakeRequest()
    closed = asyncio.Event()
    rt = SimpleNamespace(db=SimpleNamespace(sessions=session))

    def get_runtime(_request: Request) -> SimpleNamespace:
        return rt

    monkeypatch.setattr(events, "runtime", get_runtime)

    async def source(_db: Any, owner: str, cursor: int) -> AsyncGenerator[dict[str, Any], None]:
        assert owner == "owner" and cursor == 12
        try:
            yield {"cursor": 13, "kind": "message.created", "payload": {"content": "صباح الخير"}}
            await asyncio.Future()
        finally:
            closed.set()

    monkeypatch.setattr(events, "stream_events", source)
    iterator = events.event_lines(cast(Request, request), "owner", 12)
    first = await anext(iterator)
    assert "event: ready" in first and '"cursor": 12' in first
    second = await anext(iterator)
    assert second.startswith("id: 13\n") and "صباح الخير" in second
    await iterator.aclose()
    assert closed.is_set()


@pytest.mark.asyncio
async def test_idle_sse_heartbeats_and_revocation_close_without_events(
    monkeypatch: pytest.MonkeyPatch,
):
    request = FakeRequest()
    closed = asyncio.Event()
    revoked = False

    def get_runtime(_request: Request) -> SimpleNamespace:
        return SimpleNamespace(db=SimpleNamespace(sessions=session))

    monkeypatch.setattr(events, "runtime", get_runtime)
    monkeypatch.setattr(events, "AUTH_REFRESH_SECONDS", 0.01)
    monkeypatch.setattr(events, "KEEPALIVE_SECONDS", 0.01)

    async def authorize(_session: Any, token: str | None):
        assert token == "test-session-only"
        if revoked:
            raise LonoraError("session_invalid", 401)
        return SimpleNamespace(id="owner")

    async def source(*_: Any) -> AsyncGenerator[dict[str, Any], None]:
        try:
            await asyncio.Future()
            yield {}
        finally:
            closed.set()

    monkeypatch.setattr(events, "read_session", authorize)
    monkeypatch.setattr(events, "stream_events", source)
    iterator = events.event_lines(cast(Request, request), "owner", 0)
    assert "event: ready" in await anext(iterator)
    async with asyncio.timeout(1):
        assert await anext(iterator) == ": keepalive\n\n"
        revoked = True
        with pytest.raises(StopAsyncIteration):
            await anext(iterator)
    assert closed.is_set()


@pytest.mark.asyncio
async def test_live_baseline_captured_before_ready_and_reconnect_does_not_skip(
    monkeypatch: pytest.MonkeyPatch,
):
    captured: list[str] = []
    rt = SimpleNamespace(db=SimpleNamespace(sessions=session))

    def get_runtime(_request: Request) -> SimpleNamespace:
        return rt

    monkeypatch.setattr(events, "runtime", get_runtime)

    async def baseline(_session: Any, owner: str) -> int:
        assert owner == "owner"
        captured.append("baseline")
        return 100

    monkeypatch.setattr(events, "current_event_cursor", baseline)
    owner = cast(Any, SimpleNamespace(id="owner"))
    request = cast(Request, FakeRequest())
    response = await events.stream(request, cursor=0, live=True, owner=owner)
    assert captured == ["baseline"]
    body = cast(AsyncGenerator[str, None], response.body_iterator)
    frame = await anext(body)
    assert '"cursor": 100' in str(frame)
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-accel-buffering"] == "no"
    assert response.headers["cache-control"] == "no-cache, no-transform"
    await body.aclose()
    response = await events.stream(request, cursor=42, live=False, owner=owner)
    assert captured == ["baseline"]
    body = cast(AsyncGenerator[str, None], response.body_iterator)
    frame = str(await anext(body))
    assert json.loads(frame.split("data: ", 1)[1])["cursor"] == 42
    await body.aclose()
