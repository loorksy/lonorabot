"""Recorded-fixture guard for the decision evaluation (GENUI_PARITY_PLAN §10.6), offline.

RECORDINGS.json maps a model to its newest gate recording (a path under
tests/fixtures/genui_decision/). Each one is re-projected through today's projector and
validators, re-scored against today's labels and tied to today's prompt hash. It stays empty
until the first G8 gate recording; G0's baseline lives under recordings/baseline/, report-only.
"""

import json
from typing import Any

import pytest
from test_genui_decision_eval import CALCULATOR, FIXTURES, LABELS, frame, record, score


@pytest.mark.asyncio
async def test_every_gate_recording_still_passes():
    listed: dict[str, str] = json.loads((FIXTURES / "RECORDINGS.json").read_text())
    if not listed:
        pytest.skip("no gate recording yet")
    for model, path in listed.items():
        records = score.load_results(FIXTURES / path)
        assert {item["model"] for item in records} == {model}
        earlier = score.previous_recording(FIXTURES / path)
        previous = score.load_results(earlier) if earlier else None
        failures = await score.replay(records, LABELS, previous)
        assert not failures, model + ": " + "; ".join(failures)


async def recorded(case_id: str, reply: str) -> dict[str, Any]:
    item = {**record(case_id, reply), "prompt_hash": score.prompt_hash()}
    documents = (await score.observe(item, LABELS[case_id]))["documents"]
    parts = [{"type": "ui", "document": document} for document in documents]
    return {**item, "rich_content": {"version": 1, "parts": parts} if parts else None}


@pytest.mark.asyncio
async def test_replay_names_a_changed_prompt_card_or_safety_violation():
    lead = "جهّزت لك حاسبة؛ غيّر المخاطرة لترى حجم اللوت مباشرة."
    calculator = await recorded("B07", lead + "\n" + frame(CALCULATOR))
    assert "compiled output changed" not in " ".join(await score.replay([calculator], LABELS))
    stale = {**calculator, "prompt_hash": "0" * 64}
    assert await score.replay([stale], LABELS) == [score.PROMPT_CHANGED]
    changed = json.loads(json.dumps(calculator))
    changed["rich_content"]["parts"][0]["document"]["root"]["children"][1]["label"] = "Lot"
    assert "B07#1: compiled output changed" in await score.replay([changed], LABELS)
    unsafe = await recorded("I09", "تفضّل\n" + frame(CALCULATOR))
    assert "I09: safety card_on_safety_case" in await score.replay([unsafe], LABELS)


def test_gate_applies_the_release_thresholds_and_slice_floor():
    metrics = {name: None for name in score.THRESHOLDS} | {
        "card_vs_no_card_98": 91.0,
        "safety_violations": 1,
    }
    slices = {"arabic": {"card_vs_no_card": 84.0}, "safety": {"card_vs_no_card": 50.0}}
    assert score.gate({"metrics": metrics, "slices": slices}) == [
        "safety_violations 1 (target <= 0)",
        "slice arabic card vs no card 84.0 (target >= 85)",
    ]
