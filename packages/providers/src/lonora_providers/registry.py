from collections.abc import Callable

from lonora_adapter_kit.model import ModelAdapter
from lonora_adapters.models.anthropic import AnthropicAdapter
from lonora_adapters.models.compatible_endpoint import CompatibleEndpointAdapter
from lonora_adapters.models.deepseek import DeepSeekAdapter
from lonora_adapters.models.openai import OpenAIAdapter
from lonora_adapters.models.openrouter import OpenRouterAdapter
from lonora_adapters.models.zai import ZaiAdapter
from lonora_core.user_error import LonoraError

PROVIDERS: dict[str, Callable[..., ModelAdapter]] = {
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "deepseek": DeepSeekAdapter,
    "zai": ZaiAdapter,
    "openrouter": OpenRouterAdapter,
    "openai_compatible": CompatibleEndpointAdapter,
}
# Providers whose base URL is the owner's, not fixed in the adapter.
OWNER_ENDPOINT = frozenset({"openai_compatible"})


def model_adapter(provider: str, api_key: str, base_url: str | None = None) -> ModelAdapter:
    adapter = PROVIDERS.get(provider)
    if adapter is None:
        raise LonoraError("provider_not_supported", 404)
    if provider in OWNER_ENDPOINT:
        if not base_url:
            raise LonoraError("model_not_configured", 409)
        return adapter(api_key, base_url)
    return adapter(api_key)


def build_adapter(
    factory: Callable[..., ModelAdapter], provider: str, secret: str, base_url: str | None
) -> ModelAdapter:
    """``factory(provider, secret)``, with the owner's base URL when the provider has one."""
    if base_url is None:
        return factory(provider, secret)
    return factory(provider, secret, base_url)
