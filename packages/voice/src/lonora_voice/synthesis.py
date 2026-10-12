import io
import wave

import numpy as np
from lonora_adapters.voice.tts import OpenAITextToSpeech
from lonora_db.client import Database
from lonora_providers.credentials import ProviderCredentials

from .routing import voice_routes


async def synthesize(db: Database, credentials: ProviderCredentials, text: str) -> bytes:
    _, tts = await voice_routes(db)
    adapter = OpenAITextToSpeech(await credentials.resolve(tts.provider))
    return await adapter.synthesize(text[:8000], tts.model, "alloy")


def pcm_24000(audio: bytes) -> bytes:
    with wave.open(io.BytesIO(audio), "rb") as wav:
        rate, channels, width = wav.getframerate(), wav.getnchannels(), wav.getsampwidth()
        if width != 2:
            raise ValueError("unsupported_audio_sample_width")
        values = np.frombuffer(wav.readframes(wav.getnframes()), dtype=np.int16).astype(np.float64)
    if channels > 1:
        values = values.reshape(-1, channels).mean(axis=1)
    if rate != 24000 and len(values) > 1:
        target = np.linspace(0, len(values) - 1, int(len(values) * 24000 / rate))
        values = np.interp(target, np.arange(len(values)), values)
    return np.clip(values, -32768, 32767).astype(np.int16).tobytes()
