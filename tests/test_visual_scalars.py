"""The stored v1 contract: legacy text bindings and structural diagnostics (rendering only;
the clients evaluate v1 scalars, tests/web/visual-scalars.test.ts)."""

from copy import deepcopy
from typing import Any

import pytest
from lonora_contracts.visual_response import VisualDocument
from pydantic import ValidationError


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
