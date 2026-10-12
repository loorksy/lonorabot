from lonora_adapter_kit.channel import ChannelAdapter
from lonora_contracts.events import EventEnvelope

from .outbound import channel_projection


async def deliver_notification(
    adapter: ChannelAdapter, destination: str, event: EventEnvelope
) -> bool:
    content = channel_projection(event)
    if content is None:
        return False
    await adapter.send(destination, content)
    return True
