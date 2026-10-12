import asyncio
from typing import cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from lonora_auth.sessions import read_session
from lonora_bus.durable_events import stream_events
from lonora_core.user_error import LonoraError

from ..runtime import ApiRuntime

router = APIRouter()


@router.websocket("/ws/events")
async def events(socket: WebSocket) -> None:
    rt = cast(ApiRuntime, socket.app.state.runtime)
    origin = socket.headers.get("origin")
    if origin and origin != rt.settings.allowed_origin:
        await socket.close(1008)
        return
    await socket.accept()
    try:
        auth = await asyncio.wait_for(socket.receive_json(), 10)
        async with rt.db.sessions() as session:
            owner = await read_session(
                session, auth.get("token") or socket.cookies.get("lonora_session")
            )
        cursor = max(0, int(auth.get("cursor", 0)))
        async for event in stream_events(rt.db, owner.id, cursor):
            await socket.send_json(event)
    except (LonoraError, WebSocketDisconnect, TimeoutError, ValueError):
        await socket.close(1008)
