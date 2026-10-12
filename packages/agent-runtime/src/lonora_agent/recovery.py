from typing import Any

from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_core.user_error import LonoraError


def restore_execution(state: dict[str, Any]) -> tuple[list[ModelMessage], list[ToolCall]]:
    try:
        return [ModelMessage.model_validate(value) for value in state.get("messages", [])], [
            ToolCall.model_validate(value) for value in state.get("pending", [])
        ]
    except ValueError:
        raise LonoraError("run_checkpoint_invalid", 500) from None
