from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.voice import VoiceSessionCreate, VoiceTranscript
from lonora_core.user_error import LonoraError
from lonora_db.voice import VoiceSessionRepository
from lonora_voice.barge_in import barge_in
from lonora_voice.sessions import create_voice_session, end_voice_session
from lonora_voice.transcript import commit_transcript

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/voice")


@router.post("/sessions", status_code=201)
async def create(
    request: Request, body: VoiceSessionCreate, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    rt = runtime(request)
    settings = rt.settings
    if not settings.livekit_api_key or not settings.livekit_api_secret:
        raise LonoraError("voice_transport_not_configured", 409)
    return await create_voice_session(
        rt.db,
        owner.id,
        body,
        settings.livekit_url,
        settings.livekit_api_key,
        settings.livekit_api_secret.get_secret_value(),
    )


@router.delete("/sessions/{session_id}")
async def close(
    request: Request, session_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    await end_voice_session(runtime(request).db, owner.id, session_id)
    return {"closed": True}


@router.post("/sessions/{session_id}/transcript", status_code=202)
async def transcript(
    request: Request,
    session_id: str,
    body: VoiceTranscript,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session:
        row = await VoiceSessionRepository().get(session, owner.id, session_id)
    return await commit_transcript(runtime(request).db, owner.id, row.thread_id or "", body)


@router.post("/sessions/{session_id}/interrupt")
async def interrupt(
    request: Request, session_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, list[str]]:
    async with runtime(request).db.sessions() as session:
        row = await VoiceSessionRepository().get(session, owner.id, session_id)
    return {"cancelled": await barge_in(runtime(request).db, owner.id, row.thread_id or "")}


@router.get("/status")
async def status(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    settings = runtime(request).settings
    return {"transport_configured": bool(settings.livekit_api_key and settings.livekit_api_secret)}
