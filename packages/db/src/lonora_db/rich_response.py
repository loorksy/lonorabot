"""Structural revalidation at the existing durable message publication boundary."""

from typing import Any

from lonora_contracts.visual_response import SERVER_PART_TYPES, RichContent
from pydantic import ValidationError


def validated_rich_content(value: Any) -> dict[str, Any] | None:
    """Malformed display data falls back to ordinary text, never a failed Run.

    The Agent compiler owns evidence/resource admission. This final structural
    boundary uses the same contract, rejecting unknown/executable properties and
    unresolved fact references before history/SSE can expose the document.
    Every caller publishes Agent output, so the server-written parts (voice notes,
    call logs) are refused here: an Agent can never present itself as one.
    """
    if value is None:
        return None
    try:
        parsed = RichContent.model_validate(value)
        if any(part.type in SERVER_PART_TYPES for part in parsed.parts):
            return None
        result = parsed.model_dump(mode="json", exclude_unset=True)
        # Version is part of the wire envelope, even when its supported default
        # was inferred while validating legacy/model input.
        result["version"] = parsed.version
        return result
    except (ValidationError, ValueError, TypeError, RecursionError):
        return None


def server_rich_content(*parts: dict[str, Any]) -> dict[str, Any]:
    """Rich content the server itself writes (a voice note, a call log), validated."""
    parsed = RichContent.model_validate({"version": 1, "parts": list(parts)})
    return {**parsed.model_dump(mode="json", exclude_unset=True), "version": parsed.version}
