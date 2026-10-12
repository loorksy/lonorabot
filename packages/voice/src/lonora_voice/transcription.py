from lonora_adapters.voice.stt import OpenAISpeechToText
from lonora_db.client import Database
from lonora_providers.credentials import ProviderCredentials

from .routing import voice_routes


async def transcribe(db: Database, credentials: ProviderCredentials, audio: bytes) -> str:
    stt, _ = await voice_routes(db)
    adapter = OpenAISpeechToText(await credentials.resolve(stt.provider))
    return await adapter.transcribe(audio, stt.model)
