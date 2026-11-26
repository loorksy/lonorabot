"""Native subscriptions share durable replay and the SSE admission boundary."""

import asyncio
from collections.abc import AsyncGenerator, Awaitable, Callable
from contextlib import asynccontextmanager
from types import SimpleNamespace
from typing import Any, cast

import pytest
from fastapi import WebSocket
from lonora_api.websocket import events


@asynccontextmanager
async def session() -> AsyncGenerator[None, None]:
    yield None


class Socket:
    def __init__(self, auth: Any):
        self.app = SimpleNamespace(
            state=SimpleNamespace(
                runtime=SimpleNamespace(
                    db=SimpleNamespace(sessions=session),
                    settings=SimpleNamespace(allowed_origin="https://lonora.test"),
                )
            )
        )
        self.headers: dict[str, str] = {}
        self.cookies: dict[str, str] = {}
        self.auth = auth
        self.sent: list[dict[str, Any]] = []
        self.closed: list[int] = []
        self.accepted = False

    async def accept(self) -> None:
        self.accepted = True

    async def receive_json(self) -> Any:
        return self.auth

    async def send_json(self, value: dict[str, Any]) -> None:
        self.sent.append(value)

    async def close(self, code: int) -> None:
        self.closed.append(code)


@pytest.mark.asyncio
@pytest.mark.parametrize("cursor,live,expected", [(0, True, 100), (42, True, 42), (0, False, 0)])
async def test_native_ready_precedes_events_and_resume_never_skips(
    monkeypatch: pytest.MonkeyPatch, cursor: int, live: bool, expected: int
):
    socket = Socket({"token": "test-session", "cursor": cursor, "live": live})
    stages: list[str] = []

    async def authorize(_session: Any, token: str | None):
        assert token == "test-session"
        stages.append("authenticated")
        return SimpleNamespace(id="owner")

    async def baseline(_session: Any, owner: str) -> int:
        assert owner == "owner"
        stages.append("baseline")
        return 100

    async def source(_db: Any, owner: str, after: int) -> AsyncGenerator[dict[str, Any], None]:
        assert owner == "owner" and after == expected
        assert socket.sent == [{"type": "ready", "cursor": expected}]
        # This represents a commit after the baseline but before snapshot refresh.
        yield {"cursor": expected + 1, "kind": "message.created", "payload": {}}

    async def guarded(
        _socket: WebSocket, token: str | None, sender: Callable[[], Awaitable[None]]
    ) -> None:
        assert token == "test-session"
        await sender()

    monkeypatch.setattr(events, "read_session", authorize)
    monkeypatch.setattr(events, "current_event_cursor", baseline)
    monkeypatch.setattr(events, "stream_events", source)
    monkeypatch.setattr(events, "guarded_stream", guarded)
    await events.events(cast(WebSocket, socket))
    assert stages == (["authenticated", "baseline"] if live and cursor == 0 else ["authenticated"])
    assert socket.accepted and not socket.closed
    assert socket.sent[-1]["cursor"] == expected + 1


@pytest.mark.asyncio
@pytest.mark.parametrize("cursor", [-1, True, "42", 2**63])
async def test_invalid_native_cursor_is_rejected_before_subscription(cursor: Any):
    socket = Socket({"token": "test-session", "cursor": cursor})
    await events.events(cast(WebSocket, socket))
    assert socket.closed == [1008] and socket.sent == []


@pytest.mark.asyncio
async def test_native_origin_check_still_precedes_acceptance():
    socket = Socket({"token": "test-session"})
    socket.headers["origin"] = "https://hostile.test"
    await events.events(cast(WebSocket, socket))
    assert not socket.accepted and socket.closed == [1008]


def test_native_ping_period_fits_well_inside_the_client_idle_timeout():
    # The phone reconnects after 45 s without any frame (B3).
    assert 15 <= events.PING_SECONDS <= 20


class QuietSocket(Socket):
    """Tells the test when the second ping went out."""

    def __init__(self, auth: Any):
        super().__init__(auth)
        self.two_pings = asyncio.Event()

    async def send_json(self, value: dict[str, Any]) -> None:
        await super().send_json(value)
        if self.sent.count({"type": "ping"}) >= 2:
            self.two_pings.set()


@pytest.mark.asyncio
async def test_quiet_native_stream_pings_on_schedule_without_a_cursor(
    monkeypatch: pytest.MonkeyPatch,
):
    socket = QuietSocket({"token": "test-session", "cursor": 5})
    ping = {"type": "ping"}

    async def authorize(_session: Any, _token: str | None):
        return SimpleNamespace(id="owner")

    async def source(_db: Any, _owner: str, after: int) -> AsyncGenerator[dict[str, Any], None]:
        assert after == 5
        # The ledger stays quiet until two pings went out; then one event and the end.
        await socket.two_pings.wait()
        yield {"cursor": 6, "kind": "message.created", "payload": {}}

    async def guarded(
        _socket: WebSocket, _token: str | None, sender: Callable[[], Awaitable[None]]
    ) -> None:
        await sender()

    monkeypatch.setattr(events, "PING_SECONDS", 0.01)
    monkeypatch.setattr(events, "read_session", authorize)
    monkeypatch.setattr(events, "stream_events", source)
    monkeypatch.setattr(events, "guarded_stream", guarded)
    async with asyncio.timeout(2):
        await events.events(cast(WebSocket, socket))
    assert socket.sent[0] == {"type": "ready", "cursor": 5}
    assert socket.sent[1:3] == [ping, ping]
    # A ping is never an event: it has no cursor, so a client cursor cannot move on it.
    assert [frame["cursor"] for frame in socket.sent if frame != ping] == [5, 6]
    assert not socket.closed
