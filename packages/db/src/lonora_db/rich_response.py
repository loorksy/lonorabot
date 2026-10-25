"""Structural revalidation at the existing durable message publication boundary."""

from typing import Any

from lonora_contracts.visual_response import RichContent
from pydantic import ValidationError


def validated_rich_content(value: Any) -> dict[str, Any] | None:
    """Malformed display data falls back to ordinary text, never a failed Run.

    The Agent compiler owns evidence/resource admission. This final structural
    boundary uses the same contract, rejecting unknown/executable properties and
    unresolved fact references before history/SSE can expose the document.
    """
    if value is None:
        return None
    try:
        parsed = RichContent.model_validate(value)
        result = parsed.model_dump(mode="json", exclude_unset=True)
        # Version is part of the wire envelope, even when its supported default
        # was inferred while validating legacy/model input.
        result["version"] = parsed.version
        return result
    except (ValidationError, ValueError, TypeError, RecursionError):
        return None
