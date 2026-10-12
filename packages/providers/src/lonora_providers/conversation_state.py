from typing import Any

from lonora_adapter_kit.types import ModelMessage


def serialize_conversation(messages: list[ModelMessage]) -> list[dict[str, Any]]:
    return [message.model_dump(mode="json") for message in messages]


def restore_conversation(payload: list[dict[str, Any]]) -> list[ModelMessage]:
    return [ModelMessage.model_validate(item) for item in payload]
