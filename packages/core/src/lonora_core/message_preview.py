"""The server-derived list preview of a message: its kind and one line of text."""

from typing import Any, cast

PREVIEW_CHARS = 160


def attachment_kind(media_type: str) -> str:
    if media_type.startswith("image/"):
        return "image"
    if media_type.startswith("audio/"):
        return "voice"
    return "file"


def rich_parts(rich_content: dict[str, Any] | None) -> list[dict[str, Any]]:
    parts = cast(list[Any], (rich_content or {}).get("parts", []))
    return [cast(dict[str, Any], part) for part in parts if isinstance(part, dict)]


def rich_text(rich_content: dict[str, Any] | None) -> str:
    """The first text part of a rich answer, collapsed to one line."""
    for part in rich_parts(rich_content):
        if part.get("type") == "text":
            text = " ".join(str(part.get("text", "")).split())
            if text:
                return text
    return ""


def message_kind(rich_content: dict[str, Any] | None, attachment_kinds: list[str]) -> str:
    """card (a rich answer with a ui part), image, voice, file or text."""
    if any(part.get("type") == "ui" for part in rich_parts(rich_content)):
        return "card"
    if attachment_kinds:
        return attachment_kinds[0]
    return "text"


def message_preview(
    content: str, rich_content: dict[str, Any] | None, attachment_names: list[str]
) -> str:
    text = " ".join(content.split()) or rich_text(rich_content)
    if not text and attachment_names:
        text = attachment_names[0]
    return text[:PREVIEW_CHARS]
