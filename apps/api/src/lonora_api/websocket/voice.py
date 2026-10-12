import asyncio
from contextlib import suppress
from typing import Any, cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from lonora_auth.sessions import read_session
from lonora_contracts.voice import VoiceTranscript
from lonora_core.user_error import LonoraError
from lonora_db.voice import VoiceSessionRepository
from lonora_voice.barge_in import barge_in
from lonora_voice.transcript import commit_transcript

from ..runtime import ApiRuntime
from .events import guarded_stream

router = APIRouter()


@router.websocket("/ws/voice")
async def voice(socket: WebSocket) -> None:
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
        session_id = payload.get("session_id")
        if not isinstance(session_id, str):
            raise LonoraError("voice_session_invalid", 400)
        async with rt.db.sessions() as session:
            owner = await read_session(session, token)
            row = await VoiceSessionRepository().get(session, owner.id, session_id)

        async def receive() -> None:
            while True:
                incoming: Any = await socket.receive_json()
                if not isinstance(incoming, dict):
                    raise LonoraError("voice_event_invalid", 400)
                event = cast(dict[str, Any], incoming)
                async with rt.db.sessions() as session:
                    await read_session(session, token)
                    current = await VoiceSessionRepository().get(session, owner.id, row.id)
                    if current.payload.get("status") == "closed":
                        raise LonoraError("voice_session_closed", 409)
                if event.get("type") == "interrupt":
                    result = {"cancelled": await barge_in(rt.db, owner.id, row.thread_id or "")}
                else:
                    result = await commit_transcript(
                        rt.db,
                        owner.id,
                        row.thread_id or "",
                        VoiceTranscript.model_validate(event["transcript"]),
                    )
                await socket.send_json(result)

        await guarded_stream(socket, token, receive, listen_disconnect=False)
    except (LonoraError, WebSocketDisconnect, TimeoutError, ValueError, KeyError):
        with suppress(RuntimeError, WebSocketDisconnect):
            await socket.close(1008)
