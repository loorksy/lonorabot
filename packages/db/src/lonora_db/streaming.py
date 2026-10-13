"""Bounded, fenced reply previews. Delivery cursors remain owned by the event publisher."""

from typing import Any, cast

from lonora_contracts.runs import Lease
from lonora_core.user_error import LonoraError

from .schema import RunRow

MAX_STREAM_CHARS = 60000
STREAM_KEY = "reply_stream"


def stream_data(row: RunRow) -> dict[str, Any] | None:
    value = row.model_metadata.get(STREAM_KEY)
    return dict(cast(dict[str, Any], value)) if isinstance(value, dict) else None


def save_stream(row: RunRow, stream: dict[str, Any]) -> None:
    row.model_metadata = {**row.model_metadata, STREAM_KEY: stream}


def start_stream(row: RunRow, lease: Lease, turn_id: str) -> dict[str, Any]:
    previous = stream_data(row) or {}
    stream: dict[str, Any] = {
        "turn_id": turn_id,
        "fence": lease.fence,
        "generation": int(previous.get("generation", 0)) + 1,
        "sequence": 0,
        "text": "",
        "truncated": False,
        "phase": "streaming",
        "message_id": None,
    }
    save_stream(row, stream)
    return stream


def append_stream(row: RunRow, lease: Lease, turn_id: str, text: str) -> tuple[dict[str, Any], str]:
    stream = stream_data(row)
    if (
        stream is None
        or stream.get("turn_id") != turn_id
        or stream.get("fence") != lease.fence
        or stream.get("phase") != "streaming"
    ):
        raise LonoraError("stale_stream_turn", 409)
    current = str(stream.get("text", ""))
    delta = text[: max(0, MAX_STREAM_CHARS - len(current))]
    stream.update(
        sequence=int(stream.get("sequence", 0)) + 1,
        text=current + delta,
        truncated=bool(stream.get("truncated")) or len(delta) != len(text),
    )
    save_stream(row, stream)
    return stream, delta


def settle_stream(
    row: RunRow, phase: str, *, message_id: str | None = None, text: str | None = None
) -> dict[str, Any] | None:
    stream = stream_data(row)
    if stream is None:
        return None
    stream.update(phase=phase, message_id=message_id)
    if text is not None:
        stream.update(text=text[:MAX_STREAM_CHARS], truncated=len(text) > MAX_STREAM_CHARS)
    save_stream(row, stream)
    return stream


def stream_identity(stream: dict[str, Any]) -> dict[str, Any]:
    return {
        key: stream[key]
        for key in (
            "turn_id",
            "fence",
            "generation",
            "sequence",
            "phase",
            "message_id",
            "truncated",
        )
    }
