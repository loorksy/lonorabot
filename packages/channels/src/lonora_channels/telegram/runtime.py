from typing import Any, cast

from ..contracts import IncomingMessage


def decode_update(update: dict[str, Any], thread_id: str) -> IncomingMessage | None:
    raw = update.get("message")
    if not isinstance(raw, dict):
        return None
    message = cast(dict[str, Any], raw)
    if not isinstance(message.get("text"), str):
        return None
    return IncomingMessage(
        external_id="telegram:" + str(update["update_id"]),
        destination=str(message["chat"]["id"]),
        content=message["text"],
        thread_id=thread_id,
    )
