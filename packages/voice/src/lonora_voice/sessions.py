from typing import Any

from lonora_adapters.voice.livekit import LiveKitTransport
from lonora_contracts.voice import VoiceSessionCreate
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.transactions import owned_thread
from lonora_db.voice import VoiceSessionRepository

from .routing import voice_routes


async def create_voice_session(
    db: Database, owner_id: str, request: VoiceSessionCreate, url: str, key: str, secret: str
) -> dict[str, Any]:
    await voice_routes(db)
    if request.mode != "pipeline":
        raise LonoraError("native_voice_requires_verified_capability", 409)
    async with db.sessions() as session, session.begin():
        thread = await owned_thread(session, owner_id, request.thread_id)
        if thread.agent_id != request.agent_id:
            raise LonoraError("voice_agent_thread_mismatch", 409)
        row = await VoiceSessionRepository().create(
            session,
            owner_id,
            {"mode": "pipeline", "status": "joining"},
            agent_id=request.agent_id,
            thread_id=request.thread_id,
        )
        row.payload = {**row.payload, "room": "lonora-" + row.id}
        room = row.payload["room"]
        session_id = row.id
    token = await LiveKitTransport(key, secret).join_token(
        room, "owner:" + owner_id + ":" + session_id
    )
    return {"session_id": session_id, "room": room, "url": url, "token": token}


async def end_voice_session(db: Database, owner_id: str, session_id: str) -> None:
    async with db.sessions() as session, session.begin():
        row = await VoiceSessionRepository().get(session, owner_id, session_id, lock=True)
        row.payload = {**row.payload, "status": "closed"}
        row.version += 1
