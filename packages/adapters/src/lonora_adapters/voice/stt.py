import httpx
from lonora_core.user_error import LonoraError


class OpenAISpeechToText:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def transcribe(
        self,
        audio: bytes,
        model: str,
        *,
        media_type: str = "audio/wav",
        language: str | None = None,
    ) -> str:
        # The provider infers the container from the file name's extension.
        extension = {"audio/mpeg": "mp3", "audio/mp4": "m4a"}.get(
            media_type, media_type.removeprefix("audio/")
        )
        async with httpx.AsyncClient(timeout=90) as client:
            try:
                response = await client.post(
                    "https://api.openai.com/v1/audio/transcriptions",
                    headers={"Authorization": "Bearer " + self.api_key},
                    data={"model": model, **({"language": language} if language else {})},
                    files={"file": ("audio." + extension, audio, media_type)},
                )
                response.raise_for_status()
                value = response.json()
                text = value.get("text")
                if not isinstance(text, str):
                    raise ValueError()
                return text
            except (httpx.HTTPError, ValueError):
                raise LonoraError("voice_transcription_failed", 502) from None
