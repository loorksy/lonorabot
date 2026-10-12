from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from lonora_adapter_kit.types import ToolDefinition
from pydantic import BaseModel

from .context import ToolContext


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_type: type[BaseModel]
    handler: Callable[[ToolContext, dict[str, Any]], Awaitable[dict[str, Any]]]
    read_only: bool = False

    def definition(self) -> ToolDefinition:
        schema = self.input_type.model_json_schema()
        schema.pop("title", None)
        if self.name == "trade_execute":
            schema.get("properties", {}).pop("operation_id", None)
        return ToolDefinition(name=self.name, description=self.description, parameters=schema)
