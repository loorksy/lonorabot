from collections.abc import Awaitable, Callable
from typing import Protocol

from lonora_contracts.model_catalog import ModelDescriptor

from .types import ModelMessage, ModelReply, ToolDefinition


class ModelAdapter(Protocol):
    async def complete(
        self,
        model: str,
        messages: list[ModelMessage],
        tools: list[ToolDefinition],
        *,
        max_output_tokens: int | None = None,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> ModelReply: ...
    async def discover(self) -> list[ModelDescriptor]: ...
    async def close(self) -> None: ...
