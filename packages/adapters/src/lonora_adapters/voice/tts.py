import httpx
from lonora_core.user_error import LonoraError


class OpenAITextToSpeech:
    def __init__(self, api_key: str):
        self.api_key = api_key

    async def synthesize(self, text: str, model: str, voice: str = "alloy") -> bytes:
        async with httpx.AsyncClient(timeout=90) as client:
            try:
                response = await client.post(
                    "https://api.openai.com/v1/audio/speech",
                    headers={"Authorization": "Bearer " + self.api_key},
                    json={"model": model, "input": text, "voice": voice, "response_format": "wav"},
                )
                response.raise_for_status()
                return response.content
            except httpx.HTTPError:
                raise LonoraError("voice_synthesis_failed", 502) from None
