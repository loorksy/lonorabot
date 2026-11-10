"""Transcribe owner voice notes outside the send request (the Gateway ``voice_notes`` step).

The audio is read from the artifact store, sent to OpenAI's transcription endpoint
with the owner's provider credentials (the owner's OpenAI STT route first, then
gpt-4o-mini-transcribe, then whisper-1; Arabic language hint), and the result is
settled by ``lonora_db.voice_notes.settle_voice_note``, which then admits the Agent's
Run. No credentials, a missing file or a provider failure settles it as failed.
No transaction is held during the provider call.
"""

import logging
from collections.abc import Callable
from pathlib import Path

from lonora_adapter_kit.voice import SpeechToText
from lonora_adapters.voice.stt import OpenAISpeechToText
from lonora_contracts.model_routing import Capability
from lonora_core.message_preview import voice_part
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.messages import VOICE_MEDIA_TYPES
from lonora_db.schema import ArtifactRow, MessageRow, OwnerProfileRow
from lonora_db.voice_notes import pending_voice_notes, settle_voice_note
from lonora_providers.credentials import ProviderCredentials
from lonora_providers.routing_policy import read_policy
from lonora_security.runtime_storage import confined_path
from sqlalchemy import select

log = logging.getLogger("lonora.voice_notes")

MODELS = ("gpt-4o-mini-transcribe", "whisper-1")


async def transcription_models(db: Database) -> list[str]:
    try:
        route = (await read_policy(db)).routes.get(Capability.STT)
    except Exception:
        route = None
    chosen = [route.model] if route and route.provider == "openai" else []
    return list(dict.fromkeys([*chosen, *MODELS]))


async def transcribe_note(
    db: Database,
    credentials: ProviderCredentials,
    owner_id: str,
    message_id: str,
    artifact_root: Path,
    speech: Callable[[str], SpeechToText] = OpenAISpeechToText,
) -> str | None:
    async with db.sessions() as session:
        message = await session.get(MessageRow, message_id)
        voice = voice_part(message.rich_content) if message else None
        artifact = await session.get(ArtifactRow, str(voice["artifact_id"])) if voice else None
        # The owner's chosen language is the hint; without one the provider detects it.
        language = await session.scalar(
            select(OwnerProfileRow.reply_language).where(OwnerProfileRow.owner_id == owner_id)
        )
    if artifact is None or artifact.owner_id != owner_id:
        return None
    media_type = str(artifact.payload.get("media_type", "")).split(";")[0].strip().lower()
    path = confined_path(artifact_root, artifact.payload["key"])
    if media_type not in VOICE_MEDIA_TYPES or not path.is_file():
        return None
    try:
        adapter = speech(await credentials.resolve("openai"))
    except LonoraError:
        return None
    audio = path.read_bytes()
    for model in await transcription_models(db):
        try:
            return await adapter.transcribe(audio, model, media_type=media_type, language=language)
        except LonoraError:
            log.warning("voice_note_transcription_failed model=%s", model)
    return None


async def transcribe_pending(
    db: Database,
    credentials: ProviderCredentials,
    owner_id: str,
    artifact_root: Path,
    speech: Callable[[str], SpeechToText] = OpenAISpeechToText,
) -> int:
    """Settle every pending voice note of the owner; returns how many were settled."""
    async with db.sessions() as session:
        message_ids = await pending_voice_notes(session, owner_id)
    settled = 0
    failure: Exception | None = None
    for message_id in message_ids:
        # One broken note never holds back the notes after it.
        try:
            transcript = await transcribe_note(
                db, credentials, owner_id, message_id, artifact_root, speech
            )
            async with db.sessions() as session, session.begin():
                if await settle_voice_note(session, owner_id, message_id, transcript) is not None:
                    settled += 1
        except Exception as error:
            failure = failure or error
            log.error("voice_note_settle_failed code=%s", type(error).__name__)
    if failure:
        raise failure
    return settled
