import httpx

from .openai_compatible import OpenAICompatibleAdapter


class OpenAIAdapter(OpenAICompatibleAdapter):
    provider = "openai"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        super().__init__(api_key, "https://api.openai.com/v1", client)
