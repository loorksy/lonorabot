import asyncio
from collections.abc import Awaitable, Callable
from contextlib import suppress
from typing import Any, cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from lonora_auth.sessions import read_session
from lonora_bus.durable_events import stream_events
from lonora_core.user_error import LonoraError

from ..runtime import ApiRuntime

router = APIRouter()


async def guarded_stream(
    socket: WebSocket,
    token: str | None,
    sender: Callable[[], Awaitable[None]],
    *,
    listen_disconnect: bool = True,
) -> None:
    """Close idle streams on disconnect, revocation, expiry, or producer failure."""
    rt = cast(ApiRuntime, socket.app.state.runtime)

    async def disconnected() -> None:
        while True:
            if (await socket.receive())["type"] == "websocket.disconnect":
                return

    async def authorized() -> None:
        while True:
            await asyncio.sleep(5)
            async with rt.db.sessions() as session:
                await read_session(session, token)

    async def send() -> None:
        await sender()

    tasks = [asyncio.create_task(authorized()), asyncio.create_task(send())]
    if listen_disconnect:
        tasks.append(asyncio.create_task(disconnected()))
    close_code = 1000
    try:
        done, _ = await asyncio.wait(tasks, return_when=asyncio.FIRST_COMPLETED)
        for task in done:
            await task
    except LonoraError:
        close_code = 1008
        raise
    finally:
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        with suppress(RuntimeError, WebSocketDisconnect):
            await socket.close(close_code)


@router.websocket("/ws/events")
async def events(socket: WebSocket) -> None:
    rt = cast(ApiRuntime, socket.app.state.runtime)
    origin = socket.headers.get("origin")
    if origin and origin != rt.settings.allowed_origin:
        await socket.close(1008)
        return
    await socket.accept()
    try:
        value: Any = await asyncio.wait_for(socket.receive_json(), 10)
        if not isinstance(value, dict):
            raise LonoraError("websocket_auth_invalid", 403)
        auth = cast(dict[str, Any], value)
        token = auth.get("token") or socket.cookies.get("lonora_session")
        if token is not None and not isinstance(token, str):
            raise LonoraError("websocket_auth_invalid", 403)
        async with rt.db.sessions() as session:
            owner = await read_session(session, token)
        cursor = auth.get("cursor", 0)
        if not isinstance(cursor, int) or isinstance(cursor, bool) or cursor < 0:
            raise LonoraError("websocket_cursor_invalid", 400)

        async def send() -> None:
            async for event in stream_events(rt.db, owner.id, cursor):
                await socket.send_json(event)

        await guarded_stream(socket, token, send)
    except (LonoraError, WebSocketDisconnect, TimeoutError, ValueError):
        with suppress(RuntimeError, WebSocketDisconnect):
            await socket.close(1008)
