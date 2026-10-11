import httpx

from .config import Settings
from .schemas import ProviderId

PROVIDER_BASE_URLS: dict[ProviderId, str] = {
    "xai": "https://api.x.ai/v1",
    "openai": "https://api.openai.com/v1",
    "anthropic": "https://api.anthropic.com/v1",
    "deepseek": "https://api.deepseek.com/v1",
    "zai": "https://api.z.ai/api/paas/v4",
    "openrouter": "https://openrouter.ai/api/v1",
}


class ModelConfigurationError(RuntimeError):
    pass


class ModelProviderError(RuntimeError):
    pass


class GlobalModelRouter:
    """Routes global model work to a configured provider without exposing its key."""

    def __init__(self, settings: Settings, *, transport: httpx.AsyncBaseTransport | None = None):
        self.settings = settings
        self.transport = transport

    @property
    def configured(self) -> bool:
        return self._key is not None and bool(self.settings.model_name.strip())

    @property
    def _key(self) -> str | None:
        if self.settings.model_api_key is None:
            return None
        value = self.settings.model_api_key.get_secret_value().strip()
        return value or None

    async def respond(
        self, messages: list[dict[str, str]], *, provider: ProviderId, model_name: str
    ) -> str:
        key = self._key
        if key is None or not model_name.strip():
            raise ModelConfigurationError("model_not_configured")
        if provider not in PROVIDER_BASE_URLS:
            raise ModelConfigurationError("model_provider_not_supported")
        base_url = PROVIDER_BASE_URLS[provider]
        try:
            async with httpx.AsyncClient(timeout=90, transport=self.transport) as client:
                if provider == "anthropic":
                    payload = await self._anthropic_request(
                        client, base_url, key, model_name, messages
                    )
                    result = "".join(
                        block.get("text", "")
                        for block in payload.get("content", [])
                        if isinstance(block, dict) and block.get("type") == "text"
                    )
                else:
                    response = await client.post(
                        f"{base_url}/chat/completions",
                        headers={"Authorization": f"Bearer {key}"},
                        json={"model": model_name, "messages": messages},
                    )
                    response.raise_for_status()
                    payload = response.json()
                    result = payload["choices"][0]["message"]["content"]
        except ModelProviderError:
            raise
        except httpx.HTTPStatusError as exc:
            raise ModelProviderError("model_provider_rejected_request") from exc
        except (httpx.HTTPError, ValueError, KeyError, IndexError, TypeError) as exc:
            raise ModelProviderError("model_provider_unavailable") from exc
        if not isinstance(result, str) or not result.strip():
            raise ModelProviderError("model_provider_empty_response")
        return result

    async def discover_models(self, provider: ProviderId) -> list[dict[str, str]]:
        key = self._key
        if key is None:
            raise ModelConfigurationError("model_not_configured")
        if provider not in PROVIDER_BASE_URLS:
            raise ModelConfigurationError("model_provider_not_supported")
        base_url = PROVIDER_BASE_URLS[provider]
        headers = self._headers(provider, key)
        try:
            async with httpx.AsyncClient(timeout=30, transport=self.transport) as client:
                response = await client.get(f"{base_url}/models", headers=headers)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise ModelProviderError("model_provider_rejected_request") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelProviderError("model_provider_unavailable") from exc
        try:
            entries = payload["data"]
            result = [
                {"id": item["id"], "name": item.get("display_name", item["id"])}
                for item in entries
                if isinstance(item, dict) and isinstance(item.get("id"), str)
            ]
        except (KeyError, TypeError) as exc:
            raise ModelProviderError("model_provider_invalid_response") from exc
        if not result:
            raise ModelProviderError("model_provider_models_unavailable")
        return sorted(result, key=lambda item: item["id"].lower())

    async def _anthropic_request(
        self,
        client: httpx.AsyncClient,
        base_url: str,
        key: str,
        model_name: str,
        messages: list[dict[str, str]],
    ) -> dict:
        system = "\n\n".join(
            message["content"] for message in messages if message["role"] == "system"
        )
        conversation = [
            {"role": message["role"], "content": message["content"]}
            for message in messages
            if message["role"] in ("user", "assistant")
        ]
        response = await client.post(
            f"{base_url}/messages",
            headers=self._headers("anthropic", key),
            json={
                "model": model_name,
                "max_tokens": 4096,
                "system": system,
                "messages": conversation,
            },
        )
        response.raise_for_status()
        return response.json()

    @staticmethod
    def _headers(provider: ProviderId, key: str) -> dict[str, str]:
        if provider == "anthropic":
            return {"x-api-key": key, "anthropic-version": "2023-06-01"}
        return {"Authorization": f"Bearer {key}"}
