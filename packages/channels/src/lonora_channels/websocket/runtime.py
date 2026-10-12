from typing import Any

from ..contracts import IncomingMessage


def decode_message(payload: dict[str, Any], thread_id: str) -> IncomingMessage:
    return IncomingMessage(
        external_id="web:" + str(payload["client_nonce"]),
        destination=thread_id,
        content=payload["content"],
        thread_id=thread_id,
    )
