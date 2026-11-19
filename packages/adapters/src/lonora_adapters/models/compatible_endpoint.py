"""An OpenAI-compatible endpoint the owner names by its base URL (12.1). The URL is
checked by ``compatible_endpoint`` before any request."""

import httpx
from lonora_security.network import compatible_endpoint

from .openai_compatible import OpenAICompatibleAdapter


class CompatibleEndpointAdapter(OpenAICompatibleAdapter):
    provider = "openai_compatible"

    def __init__(self, api_key: str, base_url: str, client: httpx.AsyncClient | None = None):
        super().__init__(api_key, compatible_endpoint(base_url), client)
