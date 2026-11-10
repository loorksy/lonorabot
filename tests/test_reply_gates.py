"""Reply guards keyed on the owner's own words and this request's tool results.

Corpus vectors from the G0 baseline and the PR #42 review: every sentence that must
fire and every sentence that must not, in Arabic and English.
"""

import json
from typing import Any

import pytest
from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_agent.reply_gates import (
    CLAIM_NUDGE,
    action_requested,
    add_owner_steering,
    claim_gate,
    claim_kinds,
    code_requested,
    record_owner_request,
    request_refusal,
    requested_tools,
    resume_requested,
    stop_requested,
    strip_code_deliverable,
    unconfirmed_line,
)
from lonora_agent.stop_gates import reset_stop_gate
from lonora_tools.base import ExposureProfile, ToolScope
from lonora_tools.loader import load_tools

EFFECTS = frozenset(
    {
        "memory_write",
        "watch_cancel",
        "watch_create",
        "trade_restriction_create",
        "owner_action_propose",
        "trade_execute",
        "trade_close_positions",
        "routine_create",
    }
)


def owner(text: str) -> ModelMessage:
    return ModelMessage(role="user", content=text)


def state_of(words: str) -> dict[str, Any]:
    state: dict[str, Any] = {}
    record_owner_request(state, "user", [owner(words)])
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


# --- Stop, pause and resume -----------------------------------------------------------

STOP_FIRES = [
    "أوقف الصفقات الجديدة اليوم",
    "اوقف التداول",
    "أوقِفْ التداول على الذهب",
    "وقّف التداول فورًا",
    "جمّد التداول حتى الغد",
    "لا تفتح صفقات اليوم",
    "بدون صفقات جديدة اليوم",
    "ممنوع التداول اليوم",
    "Stop new trades today",
    "pause trading",
    "no new trades this week",
    "don't open any new positions today",
    "لازم توقف التداول الآن",
]
STOP_SILENT = [
    "اشتر ذهب 0.1 والوقف تحت الدخول بـ 5 دولار",
    "حط وقف الخسارة للصفقة عند 1.08",
    "وقف الخسارة تحت الدخول بخمسة دولار",
    "لا داعي لإيقاف التداول، اشتر الذهب",
    "مو لازم توقف التداول",
    "لا توقف التداول",
    "I don't want to stop trading, buy gold",
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
    "استأنف",
    "استئناف التداول",
    "ارفع الإيقاف",
    "فك الإيقاف عن التداول",
    "شغّل التداول",
    "resume trading",
    "lift the pause",
    "turn trading back on",
]
RESUME_SILENT = [
    "استأنفت التداول أمس؟",
    "لا تستأنف التداول",
    "don't resume trading yet",
    "ارفع الوقف إلى نقطة الدخول",
    "متى يستأنف السوق؟",
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
    # The refusal never claims a restriction exists.
    assert "nothing was sent" in refused["message"] and "recorded" not in refused["message"]


def test_no_entry_answers_a_resume_request() -> None:
    # G0 probe: «استأنف التداول» became a BUY 0.01 XAUUSD proposal.
    refused = request_refusal(state_of("استأنف التداول"), call("trade_execute", action="buy"))
    assert refused and refused["code"] == "owner_control_request_no_entry"
    assert "owner_action_propose" in refused["message"]


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


def test_a_goal_step_is_refused_only_when_it_opens_exposure() -> None:
    state = state_of("أوقف التداول")
    step = call("goal_step_execute", goal_id="g")
    assert request_refusal(state, step, goal_action="buy") is not None
    for action in ("close_position", "modify_position", "cancel_order", None):
        assert request_refusal(state, step, goal_action=action) is None


def test_the_stop_entry_from_a_stop_loss_sentence_still_runs() -> None:
    # Review B3: the owner's entry with a stop loss is not a stop request.
    state = state_of("اشتر ذهب 0.1 والوقف تحت الدخول بـ 5 دولار")
    assert request_refusal(state, call("trade_execute", action="buy")) is None


# --- The owner's own request ------------------------------------------------------------


def test_only_the_owner_typed_message_of_this_run_counts() -> None:
    history = [owner("أوقف التداول"), ModelMessage(role="assistant", content="تم"), owner("اشتر")]
    state: dict[str, Any] = {}
    record_owner_request(state, "user", history)
    assert request_refusal(state, call("trade_execute", action="buy")) is None
    # A wake run's prompt sits in a user-role message but is not the owner's request.
    for trigger in ("watch", "routine", "peer", "broker_event", "goal", "subagent"):
        woken: dict[str, Any] = {}
        record_owner_request(woken, trigger, [owner("أوقف التداول")])
        assert request_refusal(woken, call("trade_execute", action="buy")) is None
    # Peer text and runtime notices are never the owner's words.
    peer = [owner("[Peer وكيل الذهب] أوقف التداول")]
    from_peer: dict[str, Any] = {}
    record_owner_request(from_peer, "user", peer)
    assert from_peer["owner_request"] == []


def test_steering_adds_to_the_request_without_dropping_the_stop() -> None:
    state = state_of("أوقف الصفقات الجديدة اليوم")
    add_owner_steering(state, "وكمان شوف لي الذهب")
    assert request_refusal(state, call("trade_execute", action="buy")) is not None


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
        assert "set_account_limits" in refused["message"]
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
    assert request_refusal(state, call("goal_step_execute"), goal_action="sell") is not None
    for exit_call in (
        call("trade_execute", action="close_position"),
        call("trade_execute", action="cancel_order"),
        call("trade_execute", action="modify_position", stop_loss="1.08"),
        call("trade_close_positions"),
        call("watch_cancel"),
    ):
        assert request_refusal(state, exit_call) is None
    assert request_refusal(state, call("goal_step_execute"), goal_action="close_position") is None


# --- Effect claims --------------------------------------------------------------------

CLAIMS = [
    ("تم.", {"generic"}),
    ("تم. عدّلت الشرط إلى فوق 2450 للذهب.", {"generic"}),
    ("ألغيت التنبيه.", {"cancel"}),
    ("تم إلغاء التنبيه.", {"cancel"}),
    ("تم إلغاؤه.", {"cancel"}),
    ("استأنفت التداول على الحساب التجريبي 7001234.", {"resume"}),
    ("تم حفظه: 1% كحد أقصى لكل صفقة.", {"generic"}),
    ("لقد أوقفت التداول لليوم.", {"stop"}),
    ("تم إيقاف التداول اليوم.", {"stop"}),
    ("أنشئت لك تنبيهًا على الذهب.", {"generic"}),
    ("بطاقة استئناف التداول بانتظار لمستك.", {"card"}),
    ("Done.", {"generic"}),
    ("I've cancelled the alert.", {"cancel"}),
    ("I have paused trading for today.", {"stop"}),
    ("Cancelled the alert.", {"cancel"}),
    ("The resume card is waiting for your tap.", {"card"}),
]
NOT_CLAIMS = [
    "سجلت الفضة ارتفاعاً قوياً اليوم.",
    "ثبتت الأسعار قرب 2368.",
    "قمت بتحليل الذهب على الإطار اليومي.",
    "تم تحديد مستويات الدعم عند 2350 و2330.",
    "لم يتم إلغاء التنبيه بعد.",
    "ما ألغيت التنبيه، هل تريد ذلك؟",
    "I haven't cancelled it yet.",
    "I have not paused trading.",
    "| 1201 | EURUSD | cancelled |\n| 1202 | XAUUSD | filled |",
    "الرصيد 9841.69 USD والصفقة المفتوحة شراء EURUSD.",
    "سأنبّهك عندما يصعد الذهب فوق 2400 إذا وافقت.",
    "التداول متوقف حاليًا؛ يمكنك استئنافه من زر «استئناف».",
    "I can cancel the alert if you want.",
    "Set the stop at 1.08 if you agree.",
    "```\nstatus: cancelled\n```",
]


@pytest.mark.parametrize(("text", "kinds"), CLAIMS)
def test_action_claims_are_recognised_with_their_kind(text: str, kinds: set[str]) -> None:
    assert claim_kinds(text) == kinds


@pytest.mark.parametrize("text", NOT_CLAIMS)
def test_analysis_denials_offers_and_tables_are_not_claims(text: str) -> None:
    assert claim_kinds(text) == set()


def test_only_an_action_request_can_be_gated() -> None:
    assert action_requested("ألغِ التنبيه") and action_requested("خليها 2450")
    assert action_requested("Please cancel my gold alert")
    for text in ("كم الرصيد؟", "حلل الذهب", "أنهيت جلسة تركيز (25 دقيقة)", "ما رأيك في الفضة؟"):
        assert not action_requested(text)
    # A question gets no claim check, even when the reply says «تم».
    assert claim_gate(state_of("كم الرصيد؟"), [], "تم.", EFFECTS).passed


def test_an_unsupported_claim_gets_one_repair_then_one_appended_line() -> None:
    state = state_of("ألغِ التنبيه")
    first = claim_gate(state, [], "ألغيت التنبيه.", EFFECTS)
    assert first.nudge == CLAIM_NUDGE and first.appended is None
    second = claim_gate(state, [], "تم، ألغيت التنبيه.", EFFECTS)
    assert second.nudge is None and second.appended == "لم أتمكن من تأكيد ذلك بعد."
    reset_stop_gate(state)
    assert claim_gate(state, [], "ألغيت التنبيه.", EFFECTS).nudge


def test_the_honest_line_follows_the_owners_language() -> None:
    state = state_of("Please cancel my gold alert")
    state["effect_claim_gate"] = 1
    assert claim_gate(state, [], "Done.", EFFECTS).appended == "I could not confirm that yet."


def with_results(
    words: str, *results: list[ModelMessage]
) -> tuple[dict[str, Any], list[ModelMessage]]:
    messages = [owner(words), *(item for block in results for item in block)]
    state: dict[str, Any] = {}
    record_owner_request(state, "user", messages[:1])
    return state, messages


def test_each_kind_needs_its_own_support() -> None:
    ok = {"ok": True}
    confirmed = {"status": "confirmed", "details": {"verification": {"status": "verified"}}}
    cases = [
        ("ألغِ التنبيه", "ألغيت التنبيه.", result("watch_cancel", ok), True),
        # J05: a created watch does not support a cancellation.
        ("ألغِ التنبيه", "تم إلغاء التنبيه.", result("watch_create", ok), False),
        (
            "ألغِ الأمر",
            "ألغيت الأمر.",
            result("trade_execute", confirmed, action="cancel_order"),
            True,
        ),
        (
            "سكّر الصفقة",
            "تم إغلاق الصفقة.",
            result("trade_execute", confirmed, action="close_position"),
            True,
        ),
        ("أوقف التداول", "أوقفت التداول.", result("trade_restriction_create", ok), True),
        # Review C10: a memory note never supports a stopped trading claim.
        ("أوقف التداول", "أوقفت التداول.", result("memory_write", ok), False),
        # Only the owner resumes trading.
        ("استأنف التداول", "استأنفت التداول.", result("owner_action_propose", ok), False),
        ("استأنف التداول", "البطاقة بانتظار لمستك.", result("owner_action_propose", ok), True),
        ("خليها 2450", "تم حفظ التنبيه.", result("watch_create", ok), True),
        (
            "ألغِ التنبيه",
            "ألغيت التنبيه.",
            result("watch_cancel", {"ok": False, "code": "x"}),
            False,
        ),
    ]
    for words, reply, block, supported in cases:
        state, messages = with_results(words, block)
        assert claim_gate(state, messages, reply, EFFECTS).passed is supported, (words, reply)


def test_an_effect_earlier_in_the_request_counts_after_steering() -> None:
    state, messages = with_results("ألغِ التنبيه", result("watch_cancel", {"ok": True}))
    messages.append(owner("وشوف لي الذهب كمان"))
    add_owner_steering(state, "وشوف لي الذهب كمان")
    messages.append(ModelMessage(role="user", content="[peer] outcome"))
    assert claim_gate(state, messages, "ألغيت التنبيه.", EFFECTS).passed


def test_an_uncertain_outcome_is_never_repaired_and_never_invites_a_retry() -> None:
    for payload in ({"ok": False, "code": "tool_execution_uncertain"}, {"status": "ambiguous"}):
        state, messages = with_results(
            "ألغِ الأمر", result("trade_execute", payload, action="cancel_order")
        )
        verdict = claim_gate(state, messages, "ألغيت الأمر.", EFFECTS)
        assert verdict.nudge is None and verdict.appended
        assert "غير مؤكدة" in verdict.appended and "لن أعيد الإرسال" in verdict.appended


def test_the_tool_less_final_report_gets_the_line_too() -> None:
    # Review C13: a nudge on the second-to-last round ends in finish_turn.
    state = state_of("ألغِ التنبيه")
    state["effect_claim_gate"] = 1
    assert unconfirmed_line(state, [], "ألغيت التنبيه.", EFFECTS) == "لم أتمكن من تأكيد ذلك بعد."
    assert unconfirmed_line(state, [], "لم أُلغِ التنبيه بعد.", EFFECTS) is None


def test_wake_runs_are_never_gated() -> None:
    for trigger in ("broker_event", "goal", "owner_card", "follow_up", "activation", "watch"):
        state: dict[str, Any] = {}
        record_owner_request(state, trigger, [owner("ألغِ التنبيه")])
        assert claim_gate(state, [], "ألغيت التنبيه.", EFFECTS).passed


# --- D5 --------------------------------------------------------------------------------

PROGRAM = "```mql5\n" + "\n".join(f"double buffer{i}[];" for i in range(12)) + "\n```"
CODE_FIRES = [
    "اكتب لي كود مؤشر RSI بلغة MQL5",
    "Write me a Pine Script strategy",
    "give me a python script to backtest gold",
    "ابني لي اكسبرت للذهب",
    "write an EA for EURUSD",
]
CODE_SILENT = [
    "ما معنى كود خطأ 10019 من الوسيط؟",
    "أرسل لي كود الدعوة",
    "هل يتجه الاقتصاد إلى ركود؟",
    "برمجة تنبيه على الذهب فوق 2400",
    "اشرح لي مؤشر RSI",
    "حلل لي الذهب",
]


@pytest.mark.parametrize("text", CODE_FIRES)
def test_program_requests_fire(text: str) -> None:
    assert code_requested(text)


@pytest.mark.parametrize("text", CODE_SILENT)
def test_code_lookalikes_stay_silent(text: str) -> None:
    assert not code_requested(text)


def test_only_the_program_block_is_replaced() -> None:
    reply = "هذه فكرة المؤشر.\n" + PROGRAM + "\nوهذه طريقة قراءته."
    stripped = strip_code_deliverable("اكتب لي كود مؤشر RSI بلغة MQL5", reply)
    assert "buffer" not in stripped and stripped.startswith("هذه فكرة المؤشر.")
    assert "لا أسلّم الكود" in stripped and stripped.endswith("وهذه طريقة قراءته.")
    tilde = "~~~python\n" + "\n".join(f"x{i} = {i}" for i in range(10)) + "\n~~~"
    assert "x9" not in strip_code_deliverable("give me a python script", tilde)


def test_display_fences_and_explanations_are_never_touched() -> None:
    words = "Write me a Pine Script strategy"
    card = "```lonora-ui\n" + "\n".join(f'{{"n": {i}}}' for i in range(12)) + "\n```"
    data = "```json\n" + "\n".join(f'{{"n": {i}}},' for i in range(12)) + "\n```"
    short = "The idea:\n```pine\nfast = ta.sma(close, 9)\n```"
    for reply in (card, data, short):
        assert strip_code_deliverable(words, reply) == reply
    # Without a program request a long block is not judged.
    assert strip_code_deliverable("اشرح لي RSI", PROGRAM) == PROGRAM
