import asyncio
from typing import cast

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from lonora_auth.sessions import read_session
from lonora_contracts.voice import VoiceTranscript
from lonora_core.user_error import LonoraError
from lonora_db.voice import VoiceSessionRepository
from lonora_voice.barge_in import barge_in
from lonora_voice.transcript import commit_transcript

from ..runtime import ApiRuntime

router = APIRouter()


@router.websocket("/ws/voice")
async def voice(socket: WebSocket) -> None:
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
            row = await VoiceSessionRepository().get(session, owner.id, payload["session_id"])
        while True:
            event = await socket.receive_json()
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
    except (LonoraError, WebSocketDisconnect, TimeoutError, ValueError, KeyError):
        await socket.close(1008)
