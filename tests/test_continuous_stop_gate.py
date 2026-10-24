"""Ongoing responsibility cannot end with prose or buy retries by restarting."""

import json
from typing import Any

import pytest
from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_agent.stop_gates import MAXIMUM_STOP_NUDGES, apply_stop_gates, reset_stop_gate
from lonora_agent.tool_loop import external_wait_outcome, supersede_wait_siblings, wait_update
from lonora_core.user_error import LonoraError


def test_finite_work_and_conversations_keep_their_completion_semantics() -> None:
    state: dict[str, Any] = {"pending": []}
    assert not apply_stop_gates(state, continuous=False).continue_turn
    assert state == {"pending": []}


def test_ongoing_work_requires_a_real_durable_wait_without_consuming_pending_effects() -> None:
    state: dict[str, Any] = {"pending": [{"id": "existing-order"}], "rounds": 6}
    verdict = apply_stop_gates(state, continuous=True)
    assert verdict.continue_turn
    assert "task_wait" in (verdict.nudge or "")
    assert "wait_for_input" in (verdict.nudge or "")
    assert state["pending"] == [{"id": "existing-order"}]
    assert state["rounds"] == 6


def test_process_restart_and_compute_slice_do_not_reset_stop_budget() -> None:
    state: dict[str, Any] = {}
    for _ in range(MAXIMUM_STOP_NUDGES):
        assert apply_stop_gates(state, continuous=True).continue_turn
        state = json.loads(json.dumps(state))
        state["task_continuation"] = {"version": 1, "slice": 2, "rounds_per_slice": 24}
    with pytest.raises(LonoraError, match="task_wait_required"):
        apply_stop_gates(state, continuous=True)


def test_real_external_review_epoch_can_reset_bounded_stop_budget() -> None:
    state: dict[str, Any] = {}
    for _ in range(MAXIMUM_STOP_NUDGES):
        apply_stop_gates(state, continuous=True)
    reset_stop_gate(state)
    assert apply_stop_gates(state, continuous=True).continue_turn
    assert state["continuous_stop_gate"]["attempts"] == 1


def test_actual_plan_revision_allows_another_review_but_unchanged_resume_does_not() -> None:
    state: dict[str, Any] = {"task_plan_revision": 1}
    for _ in range(MAXIMUM_STOP_NUDGES):
        apply_stop_gates(state, continuous=True)
    with pytest.raises(LonoraError, match="task_wait_required"):
        apply_stop_gates(state, continuous=True)
    state["task_plan_revision"] = 2
    assert apply_stop_gates(state, continuous=True).continue_turn
    assert state["continuous_stop_gate"]["attempts"] == 1
    assert state["continuous_stop_gate"]["plan_revision"] == 2


@pytest.mark.parametrize(
    "saved",
    [
        None,
        [],
        {"version": 2, "attempts": 0},
        {"version": 1, "attempts": True},
        {"version": 1, "attempts": -1},
        {"version": 1, "attempts": MAXIMUM_STOP_NUDGES + 1},
        {"version": 1, "attempts": 0, "plan_revision": -1},
        {"version": 1, "attempts": 0, "plan_revision": 1},
    ],
)
def test_invalid_stop_budget_is_not_silently_reinitialized(saved: Any) -> None:
    with pytest.raises(LonoraError, match="task_stop_gate_state_invalid"):
        apply_stop_gates({"continuous_stop_gate": saved}, continuous=True)


def test_wait_prose_is_bound_to_actual_call_and_does_not_borrow_another_answer() -> None:
    messages = [
        ModelMessage(role="assistant", content="I will keep watching forever."),
        ModelMessage(
            role="assistant",
            content="  سأراجع السوق عند تحقق الشرط.  ",
            tool_calls=[ToolCall(id="actual-wait", name="task_wait", arguments={"kind": "timer"})],
        ),
        ModelMessage(role="tool", content='{"status":"waiting"}', tool_call_id="actual-wait"),
        ModelMessage(role="assistant", content="Unrelated later narration."),
    ]
    assert wait_update(messages, "actual-wait") == {
        "call_id": "actual-wait",
        "text": "سأراجع السوق عند تحقق الشرط.",
    }
    assert wait_update(messages, "missing") == {"call_id": "missing", "text": ""}


def test_wait_without_associated_prose_never_promotes_earlier_stop_candidate() -> None:
    messages = [
        ModelMessage(role="assistant", content="I am monitoring your account now."),
        ModelMessage(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="real-wait", name="task_wait", arguments={"kind": "timer"})],
        ),
    ]
    assert wait_update(messages, "real-wait")["text"] == ""


def test_checkpointed_wait_restores_exact_update_and_keeps_pending_sibling_identity() -> None:
    state: dict[str, Any] = {
        "selection": {"model": "scripted"},
        "pending": [{"id": "later-effect"}],
        "environment": {
            "wait": {"call_id": "wait-1", "kind": "timer"},
            "wait_update": {"call_id": "wait-1", "text": "I will review at the saved time."},
        },
    }
    outcome = external_wait_outcome(json.loads(json.dumps(state)))
    assert outcome.external_wait and not outcome.waiting
    assert outcome.text == "I will review at the saved time."
    assert outcome.metadata == {"model": "scripted", "external_wait_call_id": "wait-1"}
    assert state["pending"] == [{"id": "later-effect"}]


def test_wait_closes_tool_block_and_supersedes_unexecuted_financial_siblings() -> None:
    wait = ToolCall(id="saved-wait", name="task_wait", arguments={"kind": "timer"})
    trade = ToolCall(id="stale-financial-intent", name="trade_execute", arguments={})
    position = ToolCall(id="old-account-read", name="market_positions", arguments={})
    messages = [
        ModelMessage(role="assistant", content="", tool_calls=[wait, trade, position]),
        ModelMessage(role="tool", tool_call_id=wait.id, content='{"status":"waiting"}'),
    ]
    pending = [trade, position]
    supersede_wait_siblings(messages, pending)
    assert pending == []
    assert [message.tool_call_id for message in messages[1:]] == [wait.id, trade.id, position.id]
    for message in messages[2:]:
        result = json.loads(message.content)
        assert result["ok"] is False
        assert result["code"] == "tool_call_superseded"
        assert result["reason"] == "task_wait_requires_fresh_analysis_after_wake"


def test_legacy_wait_restores_silently_without_promoting_old_private_prose() -> None:
    outcome = external_wait_outcome(
        {"environment": {"wait": {"call_id": "old-wait", "kind": "timer"}}}
    )
    assert outcome.external_wait
    assert outcome.text == ""
    assert outcome.metadata["external_wait_call_id"] == "old-wait"


@pytest.mark.parametrize(
    "environment",
    [
        {"wait": {}},
        {"wait": {"call_id": ""}},
        {"wait": {"call_id": "real"}, "wait_update": {"call_id": "other", "text": "wrong"}},
        {"wait": {"call_id": "real"}, "wait_update": {"call_id": "real", "text": 1}},
    ],
)
def test_wait_update_identity_cannot_be_swapped(environment: dict[str, Any]) -> None:
    with pytest.raises(LonoraError, match="task_wait_identity_invalid"):
        external_wait_outcome({"environment": environment})
