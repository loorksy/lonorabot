from typing import Protocol

from lonora_contracts.model_catalog import ModelDescriptor

from .types import ModelMessage, ModelReply, ToolDefinition


class ModelAdapter(Protocol):
    async def complete(
        self, model: str, messages: list[ModelMessage], tools: list[ToolDefinition]
    ) -> ModelReply: ...
    async def discover(self) -> list[ModelDescriptor]: ...
    async def close(self) -> None: ...
