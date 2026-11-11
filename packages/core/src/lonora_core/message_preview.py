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


def voice_part(rich_content: dict[str, Any] | None) -> dict[str, Any] | None:
    """The voice part of an owner voice note, if this message is one."""
    return next((part for part in rich_parts(rich_content) if part.get("type") == "voice"), None)


# What the Agent reads for a voice note without a transcript (the server's note).
VOICE_NOTE_PENDING_TEXT = "[Voice note from the owner; its transcript is not ready yet.]"
VOICE_NOTE_FAILED_TEXT = (
    "[Voice note from the owner that the server could not transcribe. Tell the owner you "
    "could not hear it and ask them to send it again or write it.]"
)


def model_content(content: str, rich_content: dict[str, Any] | None) -> str:
    """A message's text as the Agent reads it: a voice note is its transcript or a note."""
    voice = voice_part(rich_content)
    if voice is None or content:
        return content
    return (
        VOICE_NOTE_PENDING_TEXT
        if voice.get("transcript_status") == "pending"
        else VOICE_NOTE_FAILED_TEXT
    )


def message_kind(rich_content: dict[str, Any] | None, attachment_kinds: list[str]) -> str:
    """card (a rich answer with a ui part), image, voice, file or text."""
    if any(part.get("type") == "ui" for part in rich_parts(rich_content)):
        return "card"
    if voice_part(rich_content) is not None:
        return "voice"
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
