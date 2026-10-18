from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from lonora_adapter_kit.types import ToolDefinition
from pydantic import BaseModel

from .context import ToolContext
from .environment import recovery_metadata


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    input_type: type[BaseModel]
    handler: Callable[[ToolContext, dict[str, Any]], Awaitable[dict[str, Any]]]
    read_only: bool = False
    financial: bool = False
    replay_safe: bool = False
    legacy_replay_safe: bool = False

    def environment(self, *, schema: bool = True) -> dict[str, Any]:
        result = {
            "name": self.name,
            "purpose": self.description,
            **recovery_metadata(self.read_only, self.financial),
        }
        if schema:
            result["input_schema"] = self.definition().parameters
        result["crash_replay"] = (
            "read_only"
            if self.read_only
            else "handler_receipt"
            if self.replay_safe
            else "reconcile_required"
        )
        result["legacy_checkpoint_replay"] = self.read_only or self.legacy_replay_safe
        return result

    def definition(self) -> ToolDefinition:
        schema = self.input_type.model_json_schema()
        schema.pop("title", None)
        if self.name == "trade_execute":
            schema.get("properties", {}).pop("operation_id", None)
        return ToolDefinition(name=self.name, description=self.description, parameters=schema)
