"""Native subscriptions share durable replay and the SSE admission boundary."""

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
