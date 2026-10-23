"""Bounded observations for Live client delegation, never semantic finalization.

The documented protocol supplies timestamped deltas and a delegation offset,
not a complete utterance. Stability schedules a provisional observation only.
"""

import hashlib
import math
from dataclasses import dataclass
from typing import Any

MAX_FRAGMENTS = 2048
MAX_TRANSCRIPT_CHARACTERS = 30000
TRANSCRIPT_STABILITY_SECONDS = 1.2


def timestamp(value: object) -> float | None:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    number = float(value)
    return number if math.isfinite(number) and number >= 0 else None


def transcript_fragment(event: dict[str, Any]) -> dict[str, Any] | None:
    identity, delta = event.get("event_id"), event.get("delta")
    start, end = timestamp(event.get("start_ms")), timestamp(event.get("end_ms"))
    if (
        not isinstance(identity, str)
        or not identity
        or not isinstance(delta, str)
        or start is None
        or end is None
        or start > end
        or len(delta) > MAX_TRANSCRIPT_CHARACTERS
    ):
        return None
    return {"event_id": identity, "start_ms": start, "end_ms": end, "delta": delta}


@dataclass(frozen=True)
class TranscriptWindow:
    text: str
    fingerprint: str
    event_ids: list[str]
    error: str | None


def observe_window(
    fragments: list[dict[str, Any]], lower: float, upper: float, trimmed: float = -1
) -> TranscriptWindow:
    """Do not split a fragment at an offset or infer text across an ambiguous overlap."""
    selected = sorted(
        (part for part in fragments if part["start_ms"] <= upper and part["end_ms"] > lower),
        key=lambda part: (part["start_ms"], part["end_ms"], part["event_id"]),
    )
    digest = hashlib.sha256()
    text: list[str] = []
    identities: list[str] = []
    previous: dict[str, Any] | None = None
    error = "transcript_evicted" if trimmed > lower else None
    for part in selected:
        if part["start_ms"] < lower or part["end_ms"] > upper:
            error = "transcript_crosses_boundary"
        if previous and part["start_ms"] < previous["end_ms"]:
            # Replayed identical source spans do not duplicate the utterance. A different
            # overlapping delta has no documented revision order; reject the ambiguity.
            if all(part[key] == previous[key] for key in ("start_ms", "end_ms", "delta")):
                continue
            error = "transcript_overlap"
        # Source-identical reconnect replays may get a new delivery event ID. The
        # observation fingerprint describes audio/text, while IDs remain provenance.
        digest.update(repr((part["start_ms"], part["end_ms"], part["delta"])).encode())
        identities.append(part["event_id"])
        text.append(part["delta"])
        previous = part
    spoken = "".join(text).strip()
    if len(spoken) > MAX_TRANSCRIPT_CHARACTERS:
        error = "transcript_oversized"
    if not spoken:
        error = error or "transcript_missing"
    return TranscriptWindow(spoken, digest.hexdigest(), identities, error)
