"""The end-of-turn check of a conversation (phase 3b).

Pure cases on a built transcript and the shipped tool catalogue: each condition on its
smallest transcript, everything that must hold the reply, and the bound of two per owner
message. The loop case is in test_tool_loop_execution.py.
"""

import json
from typing import Any

import pytest
from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_agent.conversation_gate import conversation_stop_gate
from lonora_agent.failure_view import failure_view
from lonora_agent.runtime_notices import notice_message
from lonora_agent.stop_gates import CONVERSATION_KEY, reset_stop_gate
from lonora_core.user_error import LonoraError
from lonora_tools.loader import load_tools

REGISTRY = load_tools()
PERMITTED = REGISTRY.names("full")
OWNER = ModelMessage(role="user", content="كم سعر الذهب الآن؟")
REPLY = ModelMessage(role="assistant", content="لا أستطيع الوصول إلى سعر الذهب.")
NOT_FOUND = {
    "ok": False,
    "code": "symbol_not_found",
    "class": "resolution",
    "retryable": False,
    "candidates": [],
    "next_actions": [{"tool": "market_symbols"}],
    "recovery": {"category": "not_found", "next_action": "inspect_existing_state"},
}
ONE_FITS = {
    "ok": False,
    "code": "watch_not_found",
    "class": "resolution",
    "retryable": True,
    "candidates": [{"id": "w1", "label": "ذهب فوق 2400"}],
    "next_actions": [{"repeat_with": {"watch_id": "w1"}}],
    "recovery": {"category": "not_found", "next_action": "follow_hint"},
}


def exchange(tool: str, result: dict[str, Any], **arguments: Any) -> list[ModelMessage]:
    call = ToolCall(id="c-" + tool + str(len(arguments)), name=tool, arguments=arguments)
    return [
        ModelMessage(role="assistant", content="", tool_calls=[call]),
        ModelMessage(role="tool", tool_call_id=call.id, content=json.dumps(result)),
    ]


def started() -> dict[str, Any]:
    return {"owner_started": True, "owner_request_start": 0}


def gate(state: dict[str, Any], *messages: ModelMessage) -> Any:
    return conversation_stop_gate(state, list(messages), REGISTRY, PERMITTED)


def test_a_read_that_named_one_next_read_continues_the_turn_once():
    state = started()
    transcript = [OWNER, *exchange("market_quote", NOT_FOUND, symbol="gold"), REPLY]
    verdict = gate(state, *transcript)
    assert verdict.continue_turn and "call market_symbols" in verdict.nudge
    assert state[CONVERSATION_KEY] == {
        "version": 1,
        "attempts": 1,
        "fired": [
            {
                "condition": "read_step_not_taken",
                "tool": "market_quote",
                "call_id": "c-market_quote1",
            }
        ],
        "exhausted": False,
    }
    # The same fact is raised once: a reply that keeps its answer after it stands.
    again = [*transcript, notice_message("conversation_check", verdict.nudge), REPLY]
    assert not gate(state, *again).continue_turn
    assert state[CONVERSATION_KEY]["attempts"] == 1


def test_a_result_that_already_lists_what_exists_or_a_step_already_taken_ends_the_turn():
    listed = {**NOT_FOUND, "candidates": [{"symbol": "XAUUSDm", "similar": True}]}
    assert not gate(
        started(), OWNER, *exchange("market_quote", listed, symbol="gold"), REPLY
    ).continue_turn
    existing = {**NOT_FOUND, "existing": [{"id": "a1"}]}
    assert not gate(
        started(), OWNER, *exchange("market_quote", existing, symbol="x"), REPLY
    ).continue_turn
    taken = [
        OWNER,
        *exchange("market_symbols", {"ok": True, "symbols": []}),
        *exchange("market_quote", NOT_FOUND, symbol="gold"),
        REPLY,
    ]
    assert not gate(started(), *taken).continue_turn
    # Only the last calls are read: an earlier miss the turn moved past is not raised.
    moved_on = [
        OWNER,
        *exchange("market_quote", NOT_FOUND, symbol="gold"),
        *exchange("web_search", {"ok": True, "results": []}, query="gold"),
        REPLY,
    ]
    assert not gate(started(), *moved_on).continue_turn
    # A change is never the step the turn is pushed to.
    change = {**NOT_FOUND, "next_actions": [{"tool": "watch_create"}]}
    assert not gate(
        started(), OWNER, *exchange("market_quote", change, symbol="x"), REPLY
    ).continue_turn


def test_a_wrong_tool_name_is_looked_up_before_the_reply_stands():
    unknown = {
        "ok": False,
        "code": "tool_call_target_unknown",
        "class": "resolution",
        "retryable": False,
        "candidates": [],
        "next_actions": [{"tool": "tool_environment"}],
    }
    verdict = gate(started(), OWNER, *exchange("tool_call", unknown, name="gold_price"), REPLY)
    assert verdict.continue_turn and "call tool_environment" in verdict.nudge


def test_one_found_tool_that_was_never_called_continues_the_turn():
    found = {"ok": True, "tools": [{"name": "market_quote", "available": True}], "total": 1}
    verdict = gate(started(), OWNER, *exchange("tool_environment", found, query="price"), REPLY)
    assert verdict.continue_turn and "market_quote" in verdict.nudge
    assert "call it now" in verdict.nudge
    # One row of a longer listing is a page of it, not the tool a lookup found.
    page = {**found, "total": 41, "next_offset": None}
    assert not gate(
        started(), OWNER, *exchange("tool_environment", page, offset=40), REPLY
    ).continue_turn
    inspected = {"ok": True, "tool": {"name": "watch_list", "available": True}}
    assert gate(
        started(), OWNER, *exchange("tool_environment", inspected, tool_name="watch_list"), REPLY
    ).continue_turn
    # Called after it was found, unavailable, or one of several: the reply stands.
    used = [
        OWNER,
        *exchange("tool_environment", found, query="price"),
        *exchange("market_quote", {"ok": True, "bid": 1}, symbol="XAUUSDm"),
        REPLY,
    ]
    assert not gate(started(), *used).continue_turn
    off = {"ok": True, "tools": [{"name": "market_quote", "available": False}], "total": 1}
    assert not gate(
        started(), OWNER, *exchange("tool_environment", off, query="p"), REPLY
    ).continue_turn
    two = {"ok": True, "tools": [{"name": "market_quote"}, {"name": "market_symbols"}]}
    assert not gate(
        started(), OWNER, *exchange("tool_environment", two, query="p"), REPLY
    ).continue_turn


def test_a_found_change_is_the_owners_to_ask_for_and_a_found_trade_is_never_raised():
    change = {"ok": True, "tools": [{"name": "watch_create", "available": True}], "total": 1}
    verdict = gate(started(), OWNER, *exchange("tool_environment", change, query="watch"), REPLY)
    assert verdict.continue_turn
    assert "If the owner only asked about it, your answer stands." in verdict.nudge
    assert "call it now" not in verdict.nudge
    for name in ("trade_execute", "trade_close_positions"):
        money = {"ok": True, "tools": [{"name": name, "available": True}], "total": 1}
        assert not gate(
            started(), OWNER, *exchange("tool_environment", money, query="close"), REPLY
        ).continue_turn


def test_changes_that_all_failed_with_a_way_to_repeat_them_continue_the_turn():
    verdict = gate(started(), OWNER, *exchange("watch_cancel", ONE_FITS, watch_id="ذهب"), REPLY)
    assert verdict.continue_turn and "watch_cancel" in verdict.nudge
    assert "nothing was changed" in verdict.nudge
    # One change went through, or the failure names no way on: the reply stands.
    partly = [
        OWNER,
        *exchange("watch_cancel", ONE_FITS, watch_id="ذهب"),
        *exchange("watch_cancel", {"ok": True, "id": "w2"}, watch_id="w2", again=True),
        REPLY,
    ]
    assert not gate(started(), *partly).continue_turn
    plain: dict[str, Any] = {"ok": False, "code": "watch_not_found", "class": "resolution"}
    assert not gate(
        started(), OWNER, *exchange("watch_cancel", plain, watch_id="x"), REPLY
    ).continue_turn
    ask = {**ONE_FITS, "next_actions": [{"ask_owner": "which_one"}]}
    assert not gate(
        started(), OWNER, *exchange("watch_cancel", ask, watch_id="x"), REPLY
    ).continue_turn
    other_change = {**ONE_FITS, "next_actions": [{"tool": "watch_pause"}]}
    assert not gate(
        started(), OWNER, *exchange("watch_cancel", other_change, watch_id="x"), REPLY
    ).continue_turn


@pytest.mark.parametrize(
    "held",
    [
        exchange("watch_list", {"ok": False, "code": "agent_paused", "class": "permission"}),
        exchange(
            "watch_list",
            {"ok": False, "code": "x", "recovery": {"category": "authorization_required"}},
        ),
        exchange("watch_list", {"ok": False, "code": "x", "recovery": {"retry_exhausted": True}}),
        exchange("watch_list", {"ok": False, "code": "guardrail_blocked", "executed": False}),
        exchange(
            "watch_create",
            {
                "ok": False,
                "code": "tool_execution_uncertain",
                "recovery": {"category": "ambiguous_mutation"},
            },
        ),
        exchange("trade_execute", {"ok": True, "status": "filled"}, symbol="XAUUSDm"),
        exchange("trade_close_positions", {"ok": False, "code": "trade_approval_rejected"}),
    ],
)
def test_a_rule_a_trade_or_a_spent_retry_anywhere_in_the_request_holds_the_reply(
    held: list[ModelMessage],
):
    transcript = [OWNER, *held, *exchange("market_quote", NOT_FOUND, symbol="gold"), REPLY]
    state = started()
    assert not gate(state, *transcript).continue_turn
    assert CONVERSATION_KEY not in state


def test_a_step_is_raised_only_for_a_tool_this_run_may_use():
    transcript = [OWNER, *exchange("market_quote", NOT_FOUND, symbol="gold"), REPLY]
    narrowed = PERMITTED - {"market_symbols"}
    assert not conversation_stop_gate(started(), transcript, REGISTRY, narrowed).continue_turn
    assert conversation_stop_gate(started(), transcript, REGISTRY, PERMITTED).continue_turn


def test_an_uncertain_financial_outcome_holds_the_reply():
    state = started()
    uncertain = exchange("trade_execute", {"ok": False, "status": "ambiguous"})
    transcript = [OWNER, *uncertain, *exchange("market_quote", NOT_FOUND, symbol="gold"), REPLY]
    assert not gate(state, *transcript).continue_turn


def test_only_a_request_the_owner_typed_is_checked():
    transcript = [OWNER, *exchange("market_quote", NOT_FOUND, symbol="gold"), REPLY]
    assert not gate({}, *transcript).continue_turn
    assert not gate({"owner_started": False}, *transcript).continue_turn
    # Work a wake brought is not a request: nothing after it is checked.
    wake = ModelMessage(role="user", content='<runtime_wake>{"kind":"watch"}</runtime_wake>')
    woken = [OWNER, REPLY, wake, *exchange("market_quote", NOT_FOUND, symbol="gold"), REPLY]
    assert not gate(started(), *woken).continue_turn
    # A reply with no call has nothing to read.
    assert not gate(started(), OWNER, REPLY).continue_turn


def test_two_continuations_per_owner_message_then_the_reply_stands():
    state = started()
    first = [OWNER, *exchange("market_quote", NOT_FOUND, symbol="gold"), REPLY]
    assert gate(state, *first).continue_turn
    second = [*first, *exchange("watch_cancel", ONE_FITS, watch_id="ذهب"), REPLY]
    assert gate(state, *second).continue_turn
    found = {"ok": True, "tools": [{"name": "watch_list", "available": True}], "total": 1}
    third = [OWNER, *exchange("tool_environment", found, query="watch"), REPLY]
    assert state[CONVERSATION_KEY]["attempts"] == 2
    assert not gate(state, *third).continue_turn
    assert state[CONVERSATION_KEY]["exhausted"] is True
    assert [entry["condition"] for entry in state[CONVERSATION_KEY]["fired"]] == [
        "read_step_not_taken",
        "changes_all_failed",
    ]
    # The owner's next message starts a new budget.
    reset_stop_gate(state)
    assert CONVERSATION_KEY not in state and gate(state, *third).continue_turn


def test_a_record_that_is_not_the_gates_own_is_refused_not_rebuilt():
    records: list[Any] = [{}, {"version": 1, "attempts": 9, "fired": [], "exhausted": False}, "x"]
    for broken in records:
        state: dict[str, Any] = {**started(), CONVERSATION_KEY: broken}
        with pytest.raises(LonoraError, match="conversation_gate_state_invalid"):
            gate(state, OWNER, *exchange("market_quote", NOT_FOUND, symbol="gold"), REPLY)


def test_no_notice_shows_a_failure_code_or_the_owners_words():
    notices: list[str] = []
    for transcript in (
        [OWNER, *exchange("market_quote", NOT_FOUND, symbol="gold"), REPLY],
        [OWNER, *exchange("watch_cancel", ONE_FITS, watch_id="ذهب"), REPLY],
    ):
        notices.append(gate(started(), *transcript).nudge or "")
    for notice in notices:
        assert "symbol_not_found" not in notice and "watch_not_found" not in notice
        assert "الذهب" not in notice and "ذهب" not in notice
        assert notice.startswith("Automated runtime check.")
    # The notice reaches the model as written: the failure view rewrites tool results only.
    message = notice_message("conversation_check", notices[0])
    assert failure_view([message])[0].content == message.content


def test_a_lead_action_with_an_empty_reply_continues_until_the_owner_hears_one_line():
    # Mandate 3.1.2: Lonora "tells the owner in one line what it did and why".
    paused = {"changed": True, "paused": True, "owner_line": "required"}
    calls = exchange("agent_control", paused, agent_id="gold", action="pause")
    empty = ModelMessage(role="assistant", content=" ")
    state = started()
    verdict = gate(state, OWNER, *calls, empty)
    assert verdict.continue_turn and "in one line" in verdict.nudge
    assert state[CONVERSATION_KEY]["fired"][0]["condition"] == "lead_action_unreported"
    # One line ends the turn; so does a lead action that changed nothing.
    line = ModelMessage(role="assistant", content="أوقفت وكيل الذهب مؤقتًا لأن السبريد اتسع.")
    assert not gate(started(), OWNER, *calls, line).continue_turn
    unchanged = exchange("agent_control", {"changed": False}, agent_id="gold", action="pause")
    assert not gate(started(), OWNER, *unchanged, empty).continue_turn
