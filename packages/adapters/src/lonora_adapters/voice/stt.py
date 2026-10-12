import httpx
from lonora_core.user_error import LonoraError


class OpenAISpeechToText:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def transcribe(self, audio: bytes, model: str) -> str:
        async with httpx.AsyncClient(timeout=90) as client:
            try:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": "Bearer " + self.api_key},
                    data={"model": model},
                    files={"file": ("audio.wav", audio, "audio/wav")},
                )
                response.raise_for_status()
                value = response.json()
                text = value.get("text")
                if not isinstance(text, str):
                    raise ValueError()
                return text
            except (httpx.HTTPError, ValueError):
                raise LonoraError("voice_transcription_failed", 502) from None
