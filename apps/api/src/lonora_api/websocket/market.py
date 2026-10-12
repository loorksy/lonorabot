import asyncio
from typing import cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from lonora_auth.sessions import read_session
from lonora_core.user_error import LonoraError
from lonora_market.broker import broker_market
from lonora_market.streaming import quote_stream

from ..runtime import ApiRuntime

router = APIRouter()


@router.websocket("/ws/market")
async def market(socket: WebSocket) -> None:
    rt = cast(ApiRuntime, socket.app.state.runtime)
    if socket.headers.get("origin") not in {None, rt.settings.allowed_origin}:
        await socket.close(1008)
        return
    await socket.accept()
    try:
        payload = await asyncio.wait_for(socket.receive_json(), 10)
        async with rt.db.sessions() as session:
            owner = await read_session(
                session, socket.cookies.get("lonora_session") or payload.get("token")
            )
        provider = await broker_market(
            rt.services(owner.id).brokers, owner.id, payload["account_id"]
        )
        async for quote in quote_stream(provider, payload["symbol"]):
            await socket.send_json(quote.model_dump(mode="json"))
    except (LonoraError, WebSocketDisconnect, TimeoutError, ValueError, KeyError):
        await socket.close(1008)
