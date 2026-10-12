from collections import deque

from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolDefinition
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_core.user_error import LonoraError


class ScriptedModelAdapter:
    """Explicit test fixture; never part of the production provider registry."""

    def __init__(self, replies: list[ModelReply]):
        self.replies = deque(replies)
        self.requests: list[list[ModelMessage]] = []

    async def complete(
        self, model: str, messages: list[ModelMessage], tools: list[ToolDefinition]
    ) -> ModelReply:
        self.requests.append(list(messages))
        if not self.replies:
            raise LonoraError("scripted_model_exhausted", 500)
        return self.replies.popleft()

    async def discover(self) -> list[ModelDescriptor]:
        return []

    async def close(self) -> None:
        self.replies.clear()
