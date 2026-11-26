import httpx

from .openai_compatible import OpenAICompatibleAdapter


class OpenRouterAdapter(OpenAICompatibleAdapter):
    provider = "openrouter"
    # OpenRouter serves its Anthropic entries on Chat Completions as well.
    wires = frozenset({"openai-completions", "anthropic-messages"})

    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        super().__init__(api_key, "https://openrouter.ai/api/v1", client)
