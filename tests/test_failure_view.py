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


def test_a_reason_the_result_already_gives_is_kept_beside_the_codes_words() -> None:
    closed = tool(
        {
            "ok": False,
            "code": "tool_call_superseded",
            "reason": "task_wait_requires_fresh_analysis_after_wake",
        }
    )
    assert json.loads(failure_view([closed])[0].content) == {
        "ok": False,
        "reason": "tool call superseded: task wait requires fresh analysis after wake",
    }


def test_an_unknown_outcome_and_a_note_are_put_in_words_without_becoming_failures() -> None:
    unknown = tool(
        {
            "status": "ambiguous",
            "operation_id": "o1",
            "recovery": {
                "category": "ambiguous_mutation",
                "next_action": "reconcile_before_any_resend",
                "safe_to_retry": False,
            },
        }
    )
    note = tool({"ok": True, "code": "no_positions", "results": []})
    seen, noted = (json.loads(m.content) for m in failure_view([unknown, note]))
    # Not known is not failed: no reason and no ok are invented for it.
    assert "reason" not in seen and "ok" not in seen and seen["status"] == "ambiguous"
    assert seen["recovery"]["next_action"] == "reconcile before any resend"
    assert noted == {"ok": True, "reason": "no positions", "results": []}


def test_everything_else_is_left_exactly_as_it_is() -> None:
    read = tool({"ok": True, "quote": {"bid": "1.1"}, "results": [{"code": None, "id": "o2"}]})
    # A code that is not one of ours (a currency, a snippet from an outside tool) stays.
    outside = tool({"ok": True, "code": "USD", "results": [{"code": "print(1)"}]})
    said = ModelMessage(role="assistant", content='the tool said "code": "symbol_not_found"')
    broken = ModelMessage(role="tool", tool_call_id="x", content='not json "code": "a_b"')
    messages = [read, outside, said, broken]
    assert failure_view(messages) == messages
