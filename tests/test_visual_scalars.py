"""Shared fixtures enforce the deterministic scalar boundary on both runtimes."""

import json
from copy import deepcopy
from pathlib import Path
from typing import Any

import pytest
from lonora_contracts.visual_response import VisualDocument
from lonora_contracts.visual_values import evaluate_extended_visual_op
from pydantic import ValidationError

CASES = json.loads((Path(__file__).parent / "fixtures" / "visual-scalars.json").read_text())


@pytest.mark.parametrize("case", CASES)
def test_bounded_scalar_fixture(case: dict[str, Any]) -> None:
    assert evaluate_extended_visual_op(case["op"], case["args"]) == case["expected"]


def test_scalar_bounds_never_coerce_missing_values_or_overflow() -> None:
    assert evaluate_extended_visual_op("concat", ["x" * 4001]) is None
    assert evaluate_extended_visual_op("concat", ["😀" * 4000]) == "😀" * 4000
    assert evaluate_extended_visual_op("concat", [10**1000]) is None
    assert evaluate_extended_visual_op("sqrt", [10**1000]) is None


def legacy() -> dict[str, Any]:
    return {
        "version": 1,
        "mode": "example",
        "state": {"symbol": "GOLD.example", "entry": 12.5},
        "root": {"id": "preview", "type": "text", "text": "Example {{symbol}} at {{entry}}"},
    }


def test_legacy_preview_is_an_explicit_reactive_expression_without_mutating_input() -> None:
    raw = legacy()
    original = deepcopy(raw)
    document = VisualDocument.model_validate(raw)
    assert raw == original
    assert document.root.text is None
    assert document.root.value == {
        "op": "concat",
        "args": ["Example ", {"state": "symbol"}, " at ", {"state": "entry"}],
    }


@pytest.mark.parametrize("alteration", ["unknown", "malformed", "label", "state", "expression"])
def test_only_known_legacy_text_bindings_are_adapted(alteration: str) -> None:
    raw = legacy()
    if alteration == "unknown":
        raw["root"]["text"] = "Example {{missing}}"
    elif alteration == "malformed":
        raw["root"]["text"] = "Example {{symbol"
    elif alteration == "label":
        raw["root"] = {"id": "value", "type": "metric", "label": "{{symbol}}", "value": 12}
    elif alteration == "state":
        raw["state"]["symbol"] = "{{missing}}"
    else:
        raw["root"] = {
            "id": "value",
            "type": "text",
            "value": {"op": "concat", "args": ["{{symbol}}"]},
        }
    with pytest.raises(ValidationError):
        VisualDocument.model_validate(raw)


def test_expression_diagnostics_include_only_a_structural_location() -> None:
    raw = legacy()
    raw["root"] = {
        "id": "value",
        "type": "metric",
        "value": {"op": "add", "args": [1, {"state": "SECRET_DO_NOT_LOG"}]},
    }
    with pytest.raises(ValidationError) as failure:
        VisualDocument.model_validate(raw)
    error = failure.value.errors(include_input=False)[0]
    assert error.get("ctx") == {"visual_path": "root.value.args.1"}
    assert "SECRET_DO_NOT_LOG" not in str(error)
