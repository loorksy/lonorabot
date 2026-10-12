import asyncio
from contextlib import suppress
from typing import Any, cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from lonora_auth.sessions import read_session
from lonora_core.user_error import LonoraError
from lonora_market.broker import broker_market
from lonora_market.streaming import quote_stream

from ..runtime import ApiRuntime
from .events import guarded_stream

router = APIRouter()


@router.websocket("/ws/market")
async def market(socket: WebSocket) -> None:
    rt = cast(ApiRuntime, socket.app.state.runtime)
    if socket.headers.get("origin") not in {None, rt.settings.allowed_origin}:
        with suppress(RuntimeError, WebSocketDisconnect):
            await socket.close(1008)
        return
    await socket.accept()
    try:
        value: Any = await asyncio.wait_for(socket.receive_json(), 10)
        if not isinstance(value, dict):
            raise LonoraError("websocket_auth_invalid", 403)
        payload = cast(dict[str, Any], value)
        token = socket.cookies.get("lonora_session") or payload.get("token")
        if token is not None and not isinstance(token, str):
            raise LonoraError("websocket_auth_invalid", 403)
        if not all(isinstance(payload.get(key), str) for key in ("account_id", "symbol")):
            raise LonoraError("market_subscription_invalid", 400)
        async with rt.db.sessions() as session:
            owner = await read_session(session, token)
        provider = await broker_market(
            rt.services(owner.id).brokers, owner.id, payload["account_id"]
        )

        async def send() -> None:
            async for quote in quote_stream(provider, payload["symbol"]):
                await socket.send_json(quote.model_dump(mode="json"))

        await guarded_stream(socket, token, send)
    except (LonoraError, WebSocketDisconnect, TimeoutError, ValueError, KeyError):
        with suppress(RuntimeError, WebSocketDisconnect):
            await socket.close(1008)
