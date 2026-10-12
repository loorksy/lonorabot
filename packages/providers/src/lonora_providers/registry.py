from lonora_adapter_kit.model import ModelAdapter
from lonora_adapters.models.anthropic import AnthropicAdapter
from lonora_adapters.models.deepseek import DeepSeekAdapter
from lonora_adapters.models.openai import OpenAIAdapter
from lonora_adapters.models.openrouter import OpenRouterAdapter
from lonora_adapters.models.zai import ZaiAdapter
from lonora_core.user_error import LonoraError

PROVIDERS = {
    "openai": OpenAIAdapter,
    "anthropic": AnthropicAdapter,
    "deepseek": DeepSeekAdapter,
    "zai": ZaiAdapter,
    "openrouter": OpenRouterAdapter,
}


def model_adapter(provider: str, api_key: str) -> ModelAdapter:
    adapter = PROVIDERS.get(provider)
    if adapter is None:
        raise LonoraError("provider_not_supported", 404)
    return adapter(api_key)
