import httpx

from .openai_compatible import OpenAICompatibleAdapter


class ZaiAdapter(OpenAICompatibleAdapter):
    provider = "zai"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        super().__init__(api_key, "https://api.z.ai/api/paas/v4", client)
