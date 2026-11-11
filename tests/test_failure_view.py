"""The model reads a failed tool result in words; the Run record keeps its codes."""

import json

from lonora_adapter_kit.types import ModelMessage
from lonora_agent.failure_view import failure_view


def tool(result: dict[str, object]) -> ModelMessage:
    return ModelMessage(role="tool", tool_call_id="c", content=json.dumps(result))


def test_a_failure_reaches_the_model_without_its_machine_code() -> None:
    failed = tool(
        {
            "ok": False,
            "code": "broker_account_not_found",
            "class": "resolution",
            "retryable": False,
            "hint": "Read what exists, then call again.",
            "next_actions": [{"tool": "market_symbols"}],
            "recovery": {
                "category": "not_found",
                "next_action": "inspect_existing_state",
                "safe_to_retry": False,
                "schema_tool": "tool_environment",
            },
        }
    )
    viewed = json.loads(failure_view([failed])[0].content)
    assert "code" not in viewed and viewed["reason"] == "broker account not found"
    assert viewed["recovery"]["category"] == "not found"
    assert viewed["recovery"]["next_action"] == "inspect existing state"
    # The model calls tools by their exact names, and the hint is the tool's own text.
    assert viewed["next_actions"] == [{"tool": "market_symbols"}]
    assert viewed["recovery"]["schema_tool"] == "tool_environment"
    assert (
        viewed["hint"] == "Read what exists, then call again." and viewed["class"] == "resolution"
    )
    # The record the gates and the logs read is not changed.
    assert json.loads(failed.content)["code"] == "broker_account_not_found"


def test_a_failed_operation_inside_a_result_is_put_in_words_too() -> None:
    order = tool(
        {
            "ok": False,
            "status": "failed",
            "code": "volume_out_of_range",
            "results": [
                {"operation_id": "o1", "status": "failed", "code": "volume_out_of_range"},
                {"operation_id": "o2", "status": "confirmed", "code": None},
            ],
        }
    )
    viewed = json.loads(failure_view([order])[0].content)
    assert viewed["reason"] == "volume out of range" and viewed["status"] == "failed"
    assert viewed["results"][0] == {
        "operation_id": "o1",
        "status": "failed",
        "reason": "volume out of range",
    }
    assert viewed["results"][1] == {"operation_id": "o2", "status": "confirmed", "code": None}


def test_everything_that_did_not_fail_is_left_exactly_as_it_is() -> None:
    read = tool({"ok": True, "code": "no_positions", "results": []})
    said = ModelMessage(role="assistant", content='the tool said "ok": false and symbol_not_found')
    broken = ModelMessage(role="tool", tool_call_id="x", content='not json "ok": false')
    assert failure_view([read, said, broken]) == [read, said, broken]
