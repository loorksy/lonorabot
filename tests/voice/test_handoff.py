"""Transport aggregation cannot certify semantic finality of Live transcripts."""

import math
from typing import Any

import pytest
from lonora_voice.handoff import observe_window, timestamp, transcript_fragment


def fragment(identity: str, start: float, end: float, text: str) -> dict[str, Any]:
    return {"event_id": identity, "start_ms": start, "end_ms": end, "delta": text}


def test_silence_after_speech_is_not_missing_transcript() -> None:
    window = observe_window([fragment("speech", 0, 700, "Analyze my account.")], -1, 1600)
    assert window.error is None
    assert window.text == "Analyze my account."
    # The window intentionally has no finalized property: even this text may be corrected.
    assert window.event_ids == ["speech"]


def test_source_order_and_replayed_span_do_not_duplicate_words() -> None:
    window = observe_window(
        [
            fragment("tail", 300, 700, "gold."),
            fragment("head", 0, 300, "Analyze "),
            fragment("head-replay", 0, 300, "Analyze "),
        ],
        -1,
        1000,
    )
    assert window.error is None and window.text == "Analyze gold."
    original = observe_window(
        [fragment("head", 0, 300, "Analyze "), fragment("tail", 300, 700, "gold.")], -1, 1000
    )
    assert window.fingerprint == original.fingerprint


@pytest.mark.parametrize(
    "parts,lower,upper,error",
    [
        (
            [fragment("head", 0, 600, "Buy"), fragment("revision", 300, 700, "Sell")],
            -1,
            900,
            "transcript_overlap",
        ),
        (
            [fragment("crossing", 600, 1100, "if the price recovers")],
            -1,
            900,
            "transcript_crosses_boundary",
        ),
        (
            [fragment("crossing", 600, 1100, "if the price recovers")],
            900,
            1400,
            "transcript_crosses_boundary",
        ),
        ([], -1, 900, "transcript_missing"),
    ],
)
def test_ambiguous_source_window_is_not_submitted(
    parts: list[dict[str, Any]], lower: float, upper: float, error: str
) -> None:
    assert observe_window(parts, lower, upper).error == error


def test_evicted_input_cannot_be_invented() -> None:
    assert (
        observe_window([fragment("tail", 500, 700, "0.1 lot")], -1, 900, 400).error
        == "transcript_evicted"
    )


@pytest.mark.parametrize("value", [math.nan, math.inf, -1, True, "1000", None])
def test_invalid_protocol_timestamps_fail_closed(value: Any) -> None:
    assert timestamp(value) is None
    assert transcript_fragment({**fragment("id", 0, 1000, "text"), "end_ms": value}) is None


def test_revision_fingerprint_changes_without_guessing_semantics() -> None:
    first = observe_window([fragment("tail", 500, 900, "gold.")], -1, 1200)
    corrected = observe_window(
        [fragment("tail", 500, 900, "gold."), fragment("head", 0, 500, "Analyze ")], -1, 1200
    )
    assert first.fingerprint != corrected.fingerprint
    assert corrected.text == "Analyze gold."
