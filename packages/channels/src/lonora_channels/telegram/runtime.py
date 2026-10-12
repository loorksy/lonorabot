from typing import Any

from ..contracts import IncomingMessage


def decode_update(update: dict[str, Any], thread_id: str) -> IncomingMessage | None:
    message = update.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("text"), str):
        return None
    return IncomingMessage(
        external_id="telegram:" + str(update["update_id"]),
        destination=str(message["chat"]["id"]),
        content=message["text"],
        thread_id=thread_id,
    )
