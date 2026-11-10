"""Reply guards keyed on the owner's own words and this request's structured results.

Corpus vectors from the G0 baseline and the PR #42 reviews, in both directions, Arabic
and English.
"""

import json
from typing import Any

import pytest
from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_agent.reply_gates import (
    CLAIM_NUDGE,
    MAXIMUM_PARTS,
    GoalTradeIntent,
    action_requested,
    add_owner_steering,
    appended_parts,
    claim_gate,
    claims_effect,
    code_requested,
    record_owner_request,
    report_line,
    request_refusal,
    requested_tools,
    resume_requested,
    stop_requested,
    strip_code_deliverable,
)
from lonora_agent.stop_gates import reset_stop_gate
from lonora_tools.base import ExposureProfile, ToolScope
from lonora_tools.loader import load_tools

EFFECTS = frozenset(
    {
        "memory_write",
        "watch_cancel",
        "watch_create",
        "watch_pause",
        "trade_restriction_create",
        "owner_action_propose",
        "trade_execute",
        "trade_close_positions",
        "goal_step_execute",
        "routine_create",
        "routine_pause",
    }
)
CHECKING = "نتيجة ذلك غير مؤكدة بعد، وأتحقق منها؛ لن أعيد الإرسال."
UNCONFIRMED = "لم أتمكن من تأكيد ذلك بعد."
VERIFIED = {"status": "confirmed", "details": {"verification": {"status": "verified"}}}


def owner(text: str) -> ModelMessage:
    return ModelMessage(role="user", content=text)


def state_of(*words: str) -> dict[str, Any]:
    state: dict[str, Any] = {}
    record_owner_request(state, "user", [owner(text) for text in words])
    return state


def call(name: str, **arguments: Any) -> ToolCall:
    return ToolCall(
        id="call_" + name + str(arguments.get("action", "")), name=name, arguments=arguments
    )


def result(name: str, payload: dict[str, Any], **arguments: Any) -> list[ModelMessage]:
    made = call(name, **arguments)
    return [
        ModelMessage(role="assistant", content="", tool_calls=[made]),
        ModelMessage(role="tool", tool_call_id=made.id, content=json.dumps(payload)),
    ]


def request(words: str, *blocks: list[ModelMessage]) -> tuple[dict[str, Any], list[ModelMessage]]:
    messages = [owner(words), *(item for block in blocks for item in block)]
    state: dict[str, Any] = {}
    record_owner_request(state, "user", messages[:1])
    return state, messages


# --- Stop, pause and resume -------------------------------------------------------------

STOP_FIRES = [
    "أوقف الصفقات الجديدة اليوم",
    "اوقف التداول",
    "أوقِفْ التداول على الذهب",
    "وقّف التداول",
    "أوقفوا التداول اليوم",
    "أوقف فتح صفقات",
    "أوقف كل التداول",
    "توقف عن التداول",
    "علّق التداول",
    "جمّد التداول حتى الغد",
    "زي ما قلت أوقف التداول اليوم",
    "Stop new trades today",
    "stop trading",
    "pause trading",
    "stop taking trades today",
    "stop opening new positions",
]
STOP_SILENT = [
    "اشتر ذهب 0.1 والوقف تحت الدخول بـ 5 دولار",
    "حط وقف الخسارة للصفقة عند 1.08",
    "وقف الخسارة تحت الدخول بخمسة دولار",
    "لا توقف التداول",
    "ما توقف التداول، كمّل",
    "لا داعي لإيقاف التداول، اشتر الذهب",
    "I don't want to stop trading, buy gold",
    "don't stop trading",
    "never pause trading for news",
    "علّق على حركة الذهب",
    "تعليقك على التداول اليوم؟",
    "move the stop loss on my trade",
    "set the SL below the entry",
    "سكّر كل صفقاتي",
    "استأنف التداول",
    "اشترِ ذهب 0.1 لوت",
    "",
]
RESUME_FIRES = [
    "استأنف التداول",
    "استئناف التداول",
    "شغّل التداول",
    "فك الإيقاف عن التداول",
    "resume trading",
    "turn trading back on",
    "lift the trading pause",
]
RESUME_SILENT = [
    "استأنف",
    "استأنفت التداول أمس؟",
    "لا تستأنف التداول",
    "ما تستأنف التداول",
    "don't resume trading yet",
    "ارفع الوقف إلى نقطة الدخول",
    "متى يستأنف السوق؟",
    "lift the pause",
    "أوقف التداول",
]


@pytest.mark.parametrize("text", STOP_FIRES)
def test_stop_requests_fire(text: str) -> None:
    assert stop_requested(text)


@pytest.mark.parametrize("text", STOP_SILENT)
def test_stop_lookalikes_stay_silent(text: str) -> None:
    assert not stop_requested(text)


@pytest.mark.parametrize("text", RESUME_FIRES)
def test_resume_requests_fire(text: str) -> None:
    assert resume_requested(text)


@pytest.mark.parametrize("text", RESUME_SILENT)
def test_resume_lookalikes_stay_silent(text: str) -> None:
    assert not resume_requested(text)


@pytest.mark.parametrize("action", ["buy", "sell", "buy_limit", "sell_stop", "modify_order"])
def test_no_entry_answers_a_stop_request(action: str) -> None:
    refused = request_refusal(
        state_of("أوقف الصفقات الجديدة اليوم"), call("trade_execute", action=action)
    )
    assert refused and refused["code"] == "owner_stop_request_no_entry"
    assert refused["executed"] is False and "trade_restriction_create" in refused["message"]
    assert "nothing was sent" in refused["message"] and "recorded" not in refused["message"]


def test_no_entry_answers_a_resume_request() -> None:
    refused = request_refusal(state_of("استأنف التداول"), call("trade_execute", action="buy"))
    assert refused and refused["code"] == "owner_control_request_no_entry"
    assert "owner_action_propose" in refused["message"]


def test_every_merged_owner_message_counts() -> None:
    # Two queued owner messages: the first says stop.
    state = state_of("أوقف التداول اليوم", "وشوف لي الذهب كمان")
    assert request_refusal(state, call("trade_execute", action="buy")) is not None
    steered = state_of("أوقف الصفقات الجديدة اليوم")
    add_owner_steering(steered, "وكمان شوف لي الذهب")
    assert request_refusal(steered, call("trade_execute", action="buy")) is not None


@pytest.mark.parametrize(
    "exit_call",
    [
        call("trade_execute", action="close_position"),
        call("trade_execute", action="modify_position", stop_loss="1.08"),
        call("trade_execute", action="cancel_order"),
        call("trade_close_positions"),
    ],
)
@pytest.mark.parametrize("words", ["أوقف التداول", "استأنف التداول", "stop trading now"])
def test_exits_are_never_blocked_by_a_control_request(words: str, exit_call: ToolCall) -> None:
    assert request_refusal(state_of(words), exit_call) is None


def test_a_goal_step_is_refused_only_when_it_increases_risk() -> None:
    state = state_of("أوقف التداول")
    step = call("goal_step_execute", goal_id="g")
    assert request_refusal(state, step, goal=GoalTradeIntent("buy")) is not None
    # Clearing a stop loss increases risk, exactly like trade_execute.
    assert request_refusal(state, step, goal=GoalTradeIntent("modify_position", True)) is not None
    for intent in (
        GoalTradeIntent("close_position"),
        GoalTradeIntent("modify_position"),
        GoalTradeIntent("cancel_order"),
        None,
    ):
        assert request_refusal(state, step, goal=intent) is None


def test_the_owners_entry_with_a_stop_loss_runs() -> None:
    state = state_of("اشتر ذهب 0.1 والوقف تحت الدخول بـ 5 دولار")
    assert request_refusal(state, call("trade_execute", action="buy")) is None


# --- The owner's own request ------------------------------------------------------------


def test_only_the_owner_typed_messages_of_this_run_count() -> None:
    history = [owner("أوقف التداول"), ModelMessage(role="assistant", content="تم"), owner("اشتر")]
    state: dict[str, Any] = {}
    record_owner_request(state, "user", history)
    assert state["owner_request"] == ["اشتر"]
    assert request_refusal(state, call("trade_execute", action="buy")) is None
    for trigger in ("watch", "routine", "peer", "broker_event", "goal", "subagent"):
        woken: dict[str, Any] = {}
        record_owner_request(woken, trigger, [owner("أوقف التداول")])
        assert request_refusal(woken, call("trade_execute", action="buy")) is None
    from_peer: dict[str, Any] = {}
    record_owner_request(from_peer, "user", [owner("[Peer وكيل الذهب] أوقف التداول")])
    assert from_peer["owner_request"] == []


# --- Promotion ------------------------------------------------------------------------


def test_the_owners_words_bring_the_control_tool_into_the_run() -> None:
    assert requested_tools(state_of("أوقف الصفقات الجديدة اليوم")) == ["trade_restriction_create"]
    assert requested_tools(state_of("ألغِ التنبيه")) == ["watch_list", "watch_cancel"]
    assert requested_tools(state_of("اختر لي نموذج الذكاء المناسب لوكيل الذهب")) == [
        "model_list",
        "model_request",
    ]
    for text in ("حلل الذهب حتى الغد", "هل هذا نموذج رأس وكتفين؟", "علّق على الذهب"):
        assert requested_tools(state_of(text)) == []


@pytest.mark.parametrize("scope", ["full", "observe_only", "helper"])
def test_promoted_control_tools_are_never_financial_and_keep_scope(scope: ToolScope) -> None:
    registry = load_tools()
    words = ["أوقف الصفقات الجديدة اليوم", "ألغِ التنبيه", "اختر نموذج الذكاء لوكيل الذهب"]
    sets: list[list[ExposureProfile]] = [["core", "market", "coordination"], ["core", "market"]]
    for profiles in sets:
        base, _ = registry.exposure(profiles, scope=scope)
        for text in words:
            remembered = requested_tools(state_of(text))
            native, _ = registry.exposure(profiles, scope=scope, remembered=remembered)
            added = set(native) - set(base)
            assert all(not registry.tools[name].financial for name in added)
            assert all(registry.tools[name].permitted(scope) for name in added)
            if scope != "helper":
                assert added == set(remembered)


# --- Limits --------------------------------------------------------------------------


def test_a_limit_the_owner_adopts_is_not_a_memory_note() -> None:
    note = call("memory_write", operations=[])
    for text in ("اعتمد 1% كحد أقصى لكل صفقة", "set my max risk per trade to 1%"):
        refused = request_refusal(state_of(text), note)
        assert refused and refused["code"] == "owner_limit_request_not_memory"
    for text in ("تذكر أنني أفضّل الردود المختصرة", "remember my max risk is 1%", "خليها 2450"):
        assert request_refusal(state_of(text), note) is None


# --- The claim repair turn never increases risk -----------------------------------------


def test_the_claim_repair_turn_refuses_only_risk_increasing_calls() -> None:
    state = state_of("ألغِ التنبيه")
    state["effect_claim_gate"] = 1
    for increasing in (
        call("trade_execute", action="buy"),
        call("trade_execute", action="modify_order"),
        call("trade_execute", action="modify_position", clear_stop_loss=True),
    ):
        refused = request_refusal(state, increasing)
        assert refused and refused["code"] == "claim_repair_no_new_risk"
    for exit_call in (
        call("trade_execute", action="close_position"),
        call("trade_execute", action="cancel_order"),
        call("trade_execute", action="modify_position", stop_loss="1.08"),
        call("trade_close_positions"),
        call("watch_cancel"),
    ):
        assert request_refusal(state, exit_call) is None


# --- Completion claims --------------------------------------------------------------

CLAIMS = [
    "تم.",
    "تم الإلغاء.",  # G0 J05, verbatim
    "تم. عدّلت الشرط إلى فوق 2450 للذهب.",
    "ألغيت التنبيه.",
    "تم إلغاء التنبيه.",
    "تم إلغاؤه.",
    "استأنفت التداول على الحساب التجريبي 7001234.",
    "تم حفظه: 1% كحد أقصى لكل صفقة.",
    "لقد أوقفت التداول لليوم.",
    "عدّلت وقف الخسارة إلى 1.0810.",
    "نقلت الهدف إلى 2420.",
    "تم تعديل جني الربح.",
    "بطاقة استئناف التداول بانتظار لمستك.",
    "Done.",
    "I've cancelled the alert.",
    "I have paused trading for today.",
    "I've moved the stop loss to 1.0810.",
    "Cancelled the alert.",
]
NOT_CLAIMS = [
    "سجلت الفضة ارتفاعاً قوياً اليوم.",
    "ثبتت الأسعار قرب 2368.",
    "قمت بتحليل الذهب على الإطار اليومي.",
    "تم تحديد مستويات الدعم عند 2350 و2330.",
    "لم يتم إلغاء التنبيه بعد.",
    "ما ألغيت التنبيه، هل تريد ذلك؟",
    "لم أعدّل وقف الخسارة بعد.",
    "I haven't cancelled it yet.",
    "I have not paused trading.",
    "| 1201 | EURUSD | cancelled |\n| 1202 | XAUUSD | filled |",
    "الرصيد 9841.69 USD والصفقة المفتوحة شراء EURUSD.",
    "سأنبّهك عندما يصعد الذهب فوق 2400 إذا وافقت.",
    "I can cancel the alert if you want.",
    "Set the stop at 1.08 if you agree.",
    "```\nstatus: cancelled\nتم.\n```",
]


@pytest.mark.parametrize("text", CLAIMS)
def test_completion_claims_are_recognised(text: str) -> None:
    assert claims_effect(text)


@pytest.mark.parametrize("text", NOT_CLAIMS)
def test_analysis_denials_offers_and_tables_are_not_claims(text: str) -> None:
    assert not claims_effect(text)


def test_only_an_action_request_is_checked() -> None:
    assert action_requested("ألغِ التنبيه") and action_requested("خليها 2450")
    for text in ("كم الرصيد؟", "حلل الذهب", "أنهيت جلسة تركيز (25 دقيقة)", "احفظ هذا"):
        assert not action_requested(text)
    assert claim_gate(state_of("كم الرصيد؟"), [], "تم.", EFFECTS).passed


@pytest.mark.parametrize(
    ("words", "reply", "block"),
    [
        ("اشترِ ذهب 0.1 لوت", "اشتريت الذهب. تم.", result("trade_execute", VERIFIED, action="buy")),
        ("سكّر الصفقة", "تم.", result("goal_step_execute", {"ok": True})),
        ("أوقف تنبيه الذهب مؤقتًا", "تم.", result("watch_pause", {"ok": True})),
        ("أوقف المراجعة الدورية", "تم.", result("routine_pause", {"ok": True})),
        (
            "شيل وقف الخسارة",
            "تم. أزلت وقف الخسارة.",
            result("trade_execute", VERIFIED, action="modify_position", clear_stop_loss=True),
        ),
        ("ألغِ التنبيه", "تم الإلغاء.", result("watch_cancel", {"ok": True})),
        # Any confirmed effect passes: no kind matching (J05's watch_create included).
        ("ألغِ التنبيه", "تم الإلغاء.", result("watch_create", {"ok": True})),
        ("استأنف التداول", "البطاقة بانتظار لمستك.", result("owner_action_propose", {"ok": True})),
    ],
)
def test_a_confirmed_effect_passes(words: str, reply: str, block: list[ModelMessage]) -> None:
    state, messages = request(words, block)
    assert claim_gate(state, messages, reply, EFFECTS).passed


@pytest.mark.parametrize(
    "payload",
    [
        {"status": "ambiguous"},
        {"ok": False, "code": "tool_execution_uncertain"},
        {"status": "submitted"},
        {"results": [{"status": "reserved"}]},
        {"ok": False, "code": "operation_ambiguous"},
    ],
)
def test_an_uncertain_effect_is_never_repaired(payload: dict[str, Any]) -> None:
    state, messages = request("اشترِ ذهب 0.1 لوت", result("trade_execute", payload, action="buy"))
    verdict = claim_gate(state, messages, "اشتريت الذهب. تم.", EFFECTS)
    assert verdict.nudge is None and verdict.appended == CHECKING


def test_memory_is_not_an_effect_and_no_effect_gets_one_repair_then_the_line() -> None:
    state, messages = request("أوقف التداول", result("memory_write", {"ok": True}))
    first = claim_gate(state, messages, "أوقفت التداول.", EFFECTS)
    assert first.nudge == CLAIM_NUDGE
    second = claim_gate(state, messages, "تم، أوقفت التداول.", EFFECTS)
    assert second.nudge is None and second.appended == UNCONFIRMED
    reset_stop_gate(state)
    assert claim_gate(state, messages, "أوقفت التداول.", EFFECTS).nudge


def test_an_effect_earlier_in_the_request_counts_after_steering() -> None:
    state, messages = request("ألغِ التنبيه", result("watch_cancel", {"ok": True}))
    messages.append(owner("وشوف لي الذهب كمان"))
    add_owner_steering(state, "وشوف لي الذهب كمان")
    messages.append(ModelMessage(role="user", content="[Peer وكيل] outcome"))
    assert claim_gate(state, messages, "ألغيت التنبيه.", EFFECTS).passed


def test_the_honest_line_follows_the_owners_language() -> None:
    state = state_of("Please cancel my gold alert")
    state["effect_claim_gate"] = 1
    assert claim_gate(state, [], "Done.", EFFECTS).appended == "I could not confirm that yet."


def test_wake_runs_are_never_checked() -> None:
    for trigger in ("broker_event", "goal", "owner_card", "follow_up", "activation", "watch"):
        state: dict[str, Any] = {}
        record_owner_request(state, trigger, [owner("ألغِ التنبيه")])
        assert claim_gate(state, [], "ألغيت التنبيه.", EFFECTS).passed


def test_a_limit_report_gets_no_line() -> None:
    state = state_of("ألغِ التنبيه")
    assert report_line(state, [], "توقفت عند حد الجولات؛ تم إيقاف العمل هنا.", EFFECTS) is None
    state["effect_claim_gate"] = 1
    assert report_line(state, [], "ألغيت التنبيه.", EFFECTS) == UNCONFIRMED


def test_a_full_card_keeps_every_part() -> None:
    card: dict[str, Any] = {"type": "ui", "document": {}}
    texts: list[Any] = [{"type": "text", "text": str(i)} for i in range(MAXIMUM_PARTS - 1)]
    parts: list[Any] = [card, *texts]
    assert len(parts) == MAXIMUM_PARTS
    kept = appended_parts(parts, UNCONFIRMED)
    assert len(kept) == MAXIMUM_PARTS and kept[0] == parts[0]
    assert kept[-1]["text"].endswith(UNCONFIRMED)
    assert appended_parts(parts[:3], UNCONFIRMED)[-1] == {"type": "text", "text": UNCONFIRMED}


# --- D5 --------------------------------------------------------------------------------

PROGRAM = "```mql5\n" + "\n".join(f"double buffer{i}[];" for i in range(12)) + "\n```"
CODE_FIRES = [
    "اكتب لي كود مؤشر RSI بلغة MQL5",
    "Write me a Pine Script strategy",
    "give me a python script to backtest gold",
    "ابني لي اكسبرت للذهب",
    "write an EA for EURUSD",
    "write me a C++ program for MT4",
    "write me a C# bot",
    "write me a trading bot",
    "اكتب لي مؤشر يرسم المتوسطات",
]
CODE_SILENT = [
    "ما معنى كود خطأ 10019 من الوسيط؟",
    "اعطني كود الدعوة",
    "هل يتجه الاقتصاد إلى ركود؟",
    "برمجة تنبيه على الذهب فوق 2400",
    "اشرح لي مؤشر RSI بلغة بسيطة",
    "اكتب لي بلغة بسيطة ما هو الرافعة",
    "what does error code 10019 mean?",
    "حلل لي الذهب",
    "write me a trading plan",
]


@pytest.mark.parametrize("text", CODE_FIRES)
def test_program_requests_fire(text: str) -> None:
    assert code_requested(text)


@pytest.mark.parametrize("text", CODE_SILENT)
def test_code_lookalikes_stay_silent(text: str) -> None:
    assert not code_requested(text)


WORDS = "Write me a Pine Script strategy"


def test_only_the_program_block_is_replaced() -> None:
    reply = "Idea first.\n" + PROGRAM + "\nHow to read it."
    stripped = strip_code_deliverable(WORDS, reply)
    assert "buffer" not in stripped and stripped.startswith("Idea first.")
    assert "I don't hand over code" in stripped and stripped.endswith("How to read it.")


def test_fence_variants_are_parsed() -> None:
    body = "\n".join(f"x{i} = {i}" for i in range(10))
    for fence in (f"~~~python\n{body}\n~~~", f"   ```cpp\n{body}\n   ```"):
        assert "x9" not in strip_code_deliverable(WORDS, "Here.\n" + fence + "\nAfter.")
    # A four-backtick fence holds ``` lines and does not swallow the rest.
    four = "````pine\n" + body + "\n```\nstill code\n````\nAfter the block."
    stripped = strip_code_deliverable(WORDS, four)
    assert "x9" not in stripped and "still code" not in stripped
    assert stripped.endswith("After the block.")


def test_display_fences_and_explanations_are_never_touched() -> None:
    long = "\n".join(f'{{"n": {i}}}' for i in range(12))
    for fence in (
        "```lonora-ui\n" + long + "\n```",
        '```lonora-ui {"version": 1}\n' + long + "\n```",
        "```json\n" + long + "\n```",
        "```mermaid\n" + long + "\n```",
        "```log\n" + long + "\n```",
        "```table\n" + long + "\n```",
        "The idea:\n```pine\nfast = ta.sma(close, 9)\n```",
    ):
        assert strip_code_deliverable(WORDS, fence) == fence
    assert strip_code_deliverable("اشرح لي RSI", PROGRAM) == PROGRAM
