from lonora_adapter_kit.channel import ChannelAdapter
from lonora_adapter_kit.registry import AdapterRegistry

from .channels.telegram import TelegramAdapter
from .channels.webhook import WebhookAdapter


def channel_registry() -> AdapterRegistry[ChannelAdapter]:
    registry: AdapterRegistry[ChannelAdapter] = AdapterRegistry()
    registry.register("telegram", TelegramAdapter)
    registry.register("webhook", WebhookAdapter)
    return registry
