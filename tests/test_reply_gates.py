"""Reply guards keyed on the owner's own words and this request's tool results (G0 baseline)."""

import json
from typing import Any

import pytest
from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_agent.reply_gates import (
    claim_gate,
    claims_effect,
    code_deliverable,
    code_requested,
    request_refusal,
    requested_tools,
    stop_requested,
)
from lonora_agent.stop_gates import reset_stop_gate

EFFECTS = frozenset({"memory_write", "watch_cancel", "trade_restriction_create"})


def owner(text: str) -> ModelMessage:
    return ModelMessage(role="user", content=text)


def call(name: str, **arguments: Any) -> ToolCall:
    return ToolCall(id="call_" + name, name=name, arguments=arguments)


def result(name: str, payload: dict[str, Any]) -> list[ModelMessage]:
    return [
        ModelMessage(role="assistant", content="", tool_calls=[call(name)]),
        ModelMessage(role="tool", tool_call_id="call_" + name, content=json.dumps(payload)),
    ]


@pytest.mark.parametrize(
    "text",
    [
        "أوقف الصفقات الجديدة اليوم",
        "اوقف التداول",
        "وقّف كل الصفقات",
        "أوقِفْ التداول على الذهب",
        "علّق التداول حتى الغد",
        "لا تفتح صفقات اليوم",
        "بدون صفقات جديدة اليوم",
        "Stop new trades today",
        "pause trading",
        "no new trades this week",
        "don't open anything today",
    ],
)
def test_the_owners_stop_or_pause_words_are_recognised(text: str) -> None:
    assert stop_requested(text)


@pytest.mark.parametrize(
    "text",
    [
        "اشتر 0.1 يورو دولار",
        "حط وقف الخسارة للصفقة عند 1.08",
        "استأنف التداول",
        "move the stop loss on my trade",
        "سكّر كل صفقاتي",
        "",
    ],
)
def test_other_requests_are_not_stop_requests(text: str) -> None:
    assert not stop_requested(text)


@pytest.mark.parametrize("action", ["buy", "sell", "buy_limit", "sell_stop", "modify_order"])
def test_no_entry_can_answer_a_stop_request(action: str) -> None:
    messages = [owner("أوقف الصفقات الجديدة اليوم")]
    refused = request_refusal(messages, call("trade_execute", action=action, symbol="EURUSD"))
    assert refused is not None
    assert refused["ok"] is False and refused["executed"] is False
    assert refused["code"] == "owner_stop_request_no_entry"
    assert "trade_restriction_create" in refused["message"]
    # A goal step may be an entry too: it does not run as the answer either.
    assert request_refusal(messages, call("goal_step_execute", goal_id="g")) is not None


@pytest.mark.parametrize("action", ["close_position", "modify_position", "cancel_order"])
def test_closing_and_protecting_stay_possible_under_a_stop_request(action: str) -> None:
    messages = [owner("stop trading now")]
    assert request_refusal(messages, call("trade_execute", action=action)) is None
    assert request_refusal(messages, call("trade_close_positions")) is None


@pytest.mark.parametrize("text", ["استأنف التداول", "استئناف التداول", "resume trading"])
def test_a_resume_request_is_never_answered_with_an_entry(text: str) -> None:
    # G0 I07: «استأنف التداول» became a BUY 0.01 XAUUSD proposal.
    refused = request_refusal([owner(text)], call("trade_execute", action="buy", symbol="XAUUSD"))
    assert refused is not None and refused["code"] == "owner_control_request_no_entry"
    assert "owner_action_propose" in refused["message"]


def test_only_the_latest_owner_message_counts() -> None:
    entry = call("trade_execute", action="buy", symbol="EURUSD")
    earlier = [owner("أوقف التداول"), ModelMessage(role="assistant", content="تم"), owner("اشتر")]
    assert request_refusal(earlier, entry) is None
    # A runtime notice or a tool observation is not the owner's word.
    notice = ModelMessage(role="user", context_origin="tool_observation", content="stop trading")
    assert request_refusal([owner("اشتر يورو"), notice], entry) is None
    assert request_refusal([owner("أوقف التداول"), notice], entry) is not None


@pytest.mark.parametrize(
    "text",
    [
        "تم.",
        "تم. عدّلت الشرط إلى فوق 2450 للذهب.",
        "ألغيت التنبيه.",
        "استأنفت التداول على الحساب التجريبي 7001234.",
        "تم حفظه: 1% كحد أقصى لكل صفقة.",
        "تم. سأجعلها للفضة على حساب التجريبي.",
        "تم. حددت الأحد الساعة 10:00 صباحًا لمراجعة الصفقات.",
        "لقد أوقفت الصفقات الجديدة.",
        "أنشئت لك تنبيهًا على الذهب.",
        "Done. The alert is set.",
        "I've cancelled the alert.",
        "I have paused trading for today.",
    ],
)
def test_effect_claims_are_recognised(text: str) -> None:
    assert claims_effect(text)


@pytest.mark.parametrize(
    "text",
    [
        "الرصيد 9841.69 USD والصفقة المفتوحة شراء EURUSD.",
        "سأنبّهك عندما يصعد الذهب فوق 2400 إذا وافقت.",
        "التداول متوقف حاليًا؛ يمكنك استئنافه من زر «استئناف».",
        "The trade that was opened yesterday is in profit.",
        "I can cancel the alert if you want.",
        "لم أنفّذ أي تغيير بعد.",
    ],
)
def test_facts_offers_and_plans_are_not_claims(text: str) -> None:
    assert not claims_effect(text)


def test_an_unsupported_claim_gets_one_repair_then_an_honest_line() -> None:
    state: dict[str, Any] = {}
    messages = [owner("ألغِ التنبيه")]
    first = claim_gate(state, messages, "ألغيت التنبيه.", EFFECTS)
    assert first.nudge and "watch_cancel" in first.nudge and first.replacement is None
    # The model insists: the claim never reaches the owner.
    second = claim_gate(state, messages, "تم، ألغيت التنبيه.", EFFECTS)
    assert second.nudge is None and second.replacement is not None
    assert not claims_effect(second.replacement)
    assert "لم" in second.replacement
    # New owner input starts a new bounded epoch.
    reset_stop_gate(state)
    assert claim_gate(state, messages, "ألغيت التنبيه.", EFFECTS).nudge


def test_english_owner_gets_the_honest_line_in_english() -> None:
    state: dict[str, Any] = {"effect_claim_gate": 1}
    verdict = claim_gate(state, [owner("Please cancel my gold alert")], "Done.", EFFECTS)
    assert verdict.replacement and verdict.replacement.startswith("Nothing")


def test_a_successful_effect_in_this_request_supports_the_claim() -> None:
    messages = [owner("ألغِ التنبيه"), *result("watch_cancel", {"ok": True, "status": "cancelled"})]
    assert claim_gate({}, messages, "ألغيت التنبيه.", EFFECTS).passed


def test_reads_failures_and_earlier_requests_do_not_support_a_claim() -> None:
    read = [owner("استأنف التداول"), *result("account_read", {"ok": True})]
    assert not claim_gate({}, read, "استأنفت التداول.", EFFECTS).passed
    failed = [owner("ألغِ التنبيه"), *result("watch_cancel", {"ok": False, "code": "x"})]
    assert not claim_gate({}, failed, "ألغيت التنبيه.", EFFECTS).passed
    earlier = [
        owner("احفظ هذا"),
        *result("memory_write", {"ok": True}),
        ModelMessage(role="assistant", content="تم حفظه."),
        owner("ألغِ التنبيه"),
    ]
    assert not claim_gate({}, earlier, "ألغيت التنبيه.", EFFECTS).passed


def test_a_cancellation_claim_needs_a_cancelling_tool() -> None:
    # G0 J05: watch_create(enabled=false), then «تم الإلغاء».
    created = [owner("ألغِ التنبيه"), *result("watch_create", {"ok": True})]
    effects = EFFECTS | {"watch_create"}
    assert not claim_gate({}, created, "تم الإلغاء.", effects).passed
    assert not claim_gate({}, created, "I've cancelled the alert.", effects).passed
    cancelled = [owner("ألغِ التنبيه"), *result("watch_cancel", {"ok": True})]
    assert claim_gate({}, cancelled, "تم الإلغاء.", effects).passed
    # Other claims still accept any successful effect.
    assert claim_gate({}, created, "تم حفظ التنبيه.", effects).passed


def test_a_limit_the_owner_adopts_is_not_a_memory_note() -> None:
    # G0 I10: «اعتمد 1% كحد أقصى لكل صفقة» became memory_write and «تم حفظه».
    note = call("memory_write", operations=[])
    for text in ("اعتمد 1% كحد أقصى لكل صفقة", "set my max risk per trade to 1%"):
        refused = request_refusal([owner(text)], note)
        assert refused and refused["code"] == "owner_limit_request_not_memory"
        assert "set_account_limits" in refused["message"]
    assert request_refusal([owner("اعتمد 1% كحد أقصى لكل صفقة")], call("account_read")) is None
    # Remembering a preference stays a memory note.
    for text in ("تذكر أنني أفضّل الردود المختصرة", "remember my max risk is 1%", "خليها 2450"):
        assert request_refusal([owner(text)], note) is None


def test_a_reply_without_a_claim_passes_untouched() -> None:
    state: dict[str, Any] = {}
    assert claim_gate(state, [owner("كم الرصيد؟")], "الرصيد 9841.69 USD.", EFFECTS).passed
    assert state == {}


MQL5 = "```mql5\n" + "\n".join(f"int line{i} = {i};" for i in range(12)) + "\n```"


def test_code_requested_by_the_owner_is_a_d5_deliverable() -> None:
    assert code_requested("اكتب لي كود مؤشر RSI بلغة MQL5")
    assert code_requested("Write me a Pine Script strategy")
    assert not code_requested("حلل لي الذهب")
    messages = [owner("اكتب لي كود مؤشر RSI بلغة MQL5")]
    assert code_deliverable(messages, "هذا هو الكود:\n" + MQL5)
    assert not code_deliverable(messages, "لا أسلّم الكود كمنتج.")


def test_a_short_block_that_explains_stays_allowed() -> None:
    # Q36: fenced code is allowed as explanation; only a deliverable is refused.
    messages = [owner("Write me a Pine Script strategy")]
    assert not code_deliverable(messages, "The idea:\n```pine\nfast = ta.sma(close, 9)\n```")
    # Without the owner asking for code, a long block is not judged here.
    assert not code_deliverable([owner("اشرح لي RSI")], MQL5)


def test_the_owners_words_bring_the_control_tool_into_the_run() -> None:
    assert requested_tools([owner("أوقف الصفقات الجديدة اليوم")]) == ["trade_restriction_create"]
    assert requested_tools([owner("ألغِ التنبيه")]) == ["watch_list", "watch_cancel"]
    assert requested_tools([owner("اختر لي نموذج الذكاء المناسب لوكيل الذهب")]) == [
        "model_list",
        "model_request",
    ]
    assert requested_tools([owner("حلل الذهب حتى الغد")]) == []


def test_hamza_forms_of_a_claim_are_recognised() -> None:
    # Probe: «تم إلغاؤه» after watch_create.
    created = [owner("ألغِ التنبيه"), *result("watch_create", {"ok": True})]
    assert claims_effect("تم إلغاؤه.")
    assert not claim_gate({}, created, "تم إلغاؤه.", EFFECTS | {"watch_create"}).passed


def test_a_waiting_card_needs_a_proposed_card() -> None:
    # Probe: I07 and I10 said the card «بانتظار لمستك» without proposing one.
    nothing = [owner("استأنف التداول"), *result("list_accounts", {"ok": True})]
    effects = EFFECTS | {"owner_action_propose", "list_accounts"}
    for text in (
        "بطاقة استئناف التداول بانتظار لمستك.",
        "The resume card is waiting for your tap.",
    ):
        assert claims_effect(text)
        assert not claim_gate({}, nothing, text, effects).passed
    proposed = [owner("استأنف التداول"), *result("owner_action_propose", {"ok": True})]
    assert claim_gate({}, proposed, "بطاقة استئناف التداول بانتظار لمستك.", effects).passed
