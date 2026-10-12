from typing import Any, Protocol


class ChannelAdapter(Protocol):
    async def send(self, destination: str, content: str) -> dict[str, Any]: ...
