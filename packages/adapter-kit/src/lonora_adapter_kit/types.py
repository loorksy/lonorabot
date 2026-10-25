from typing import Any, Literal

from lonora_contracts.domain import Contract
from lonora_contracts.usage import TokenUsage
from pydantic import Field


class ToolCall(Contract):
    id: str
    name: str
    arguments: dict[str, Any]


class ModelMessage(Contract):
    role: Literal["system", "user", "assistant", "tool"]
    # Runtime-only provenance; provider adapters serialize their explicit wire fields.
    context_origin: Literal["conversation", "tool_observation"] = "conversation"
    content: str
    # Validated display data survives checkpoints; providers serialize explicit wire fields.
    rich_content: dict[str, Any] | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list[ToolCall])
    tool_call_id: str | None = None
    images: list[str] = Field(default_factory=list[str])


class ModelReply(Contract):
    text: str = ""
    rich_content: dict[str, Any] | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list[ToolCall])
    usage: TokenUsage = Field(default_factory=TokenUsage)
    provider_metadata: dict[str, Any] = Field(default_factory=dict[str, Any])


class ToolDefinition(Contract):
    name: str
    description: str
    parameters: dict[str, Any]
