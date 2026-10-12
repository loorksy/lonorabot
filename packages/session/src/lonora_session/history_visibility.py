from typing import Any

from lonora_core.message_visibility import visible


def visible_history(messages: list[dict[str, Any]], trigger: str = "user") -> list[dict[str, Any]]:
    return [message for message in messages if visible(trigger, str(message["role"]))]
