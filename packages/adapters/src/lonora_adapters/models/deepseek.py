import httpx

from .openai_compatible import OpenAICompatibleAdapter


class DeepSeekAdapter(OpenAICompatibleAdapter):
    provider = "deepseek"

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        super().__init__(api_key, "https://api.deepseek.com/v1", client)
