import httpx

from .config import Settings


class ModelConfigurationError(RuntimeError):
    pass


class ModelProviderError(RuntimeError):
    pass


class GrokProvider:
    """Global xAI chat-completions adapter. It never exposes credentials to an agent."""

    def __init__(self, settings: Settings):
        self.settings = settings

    @property
    def configured(self) -> bool:
        return bool(
            self.settings.model_api_key
            and self.settings.model_api_key.get_secret_value().strip()
            and self.settings.model_name.strip()
        )

    async def respond(self, messages: list[dict[str, str]]) -> str:
        if not self.configured:
            raise ModelConfigurationError("model_not_configured")
        try:
            async with httpx.AsyncClient(timeout=90) as client:
                response = await client.post(
                    f"{self.settings.model_base_url.rstrip('/')}/chat/completions",
                    headers={
                        "Authorization": f"Bearer {self.settings.model_api_key.get_secret_value()}"
                    },
                    json={"model": self.settings.model_name, "messages": messages},
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPStatusError as exc:
            raise ModelProviderError("model_provider_rejected_request") from exc
        except (httpx.HTTPError, ValueError) as exc:
            raise ModelProviderError("model_provider_unavailable") from exc
        try:
            result = payload["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelProviderError("model_provider_invalid_response") from exc
        if not isinstance(result, str) or not result.strip():
            raise ModelProviderError("model_provider_empty_response")
        return result
