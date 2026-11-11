"""The acceptance harness (OWNER_BRIEF §8), deterministic layer: no model, no network.

The scorer's rules on the real replies of the owner's conversation and on good replies, the
fake MetaApi terminal under the real adapter, the scenario bank's integrity, and the
recorded baseline replayed and held strictly: a scenario listed as failing in
tests/fixtures/agent_eval/BASELINE.json must still fail with exactly those checks, so the
change that fixes one has to flip it there (and in docs/agent-eval.md). The structural
probes need a disposable PostgreSQL database and are skipped without one.
"""

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_tools.loader import load_tools
from sqlalchemy.engine import make_url

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts.agent_eval import bank, broker, score  # noqa: E402

SCENARIOS = bank.load()
TURNS = bank.conversation()
BASELINE: dict[str, Any] = json.loads((bank.FIXTURES / "BASELINE.json").read_text())
STALE = "update tests/fixtures/agent_eval/BASELINE.json and the table in docs/agent-eval.md"


def turn_record(number: int, calls: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """One reply of the owner's conversation as a recorded turn."""
    return record(TURNS[number]["content"], calls)


def record(reply: str, calls: list[dict[str, Any]] | None = None, **fields: Any) -> dict[str, Any]:
    return {
        "status": "completed",
        "owner_message": "",
        "replies": [reply],
        "rich": [None],
        "rounds": 2,
        "tool_calls": calls or [],
        "state_after": {"positions": [], "orders": [], "watches": [], "tasks": []},
        **fields,
    }


def call(tool: str, arguments: dict[str, Any] | None = None, **result: Any) -> dict[str, Any]:
    return {"tool": tool, "arguments": arguments or {}, "result": result}


def refused(tool: str, code: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    return {"tool": tool, "arguments": arguments or {}, "error": code}


ANY = {"tools": ["watch_cancel"], "expect": []}

# --- The scorer's vocabulary comes from the code ---------------------------------------


def test_the_forbidden_vocabulary_is_read_from_the_code():
    known = score.vocabulary()
    assert set(load_tools().tools) == known.tools
    assert {name for name in known.tools if "_" in name} <= known.identifiers
    # The terms the owner saw on 2026-11-11 ([10], [59], [65], [75], [77]).
    assert {"symbol_not_found", "broker_account_not_found", "owner_attention"} <= known.identifiers
    assert {"waiting", "routines", "goals", "watch"} <= known.words
    assert "watch_cancel" in known.identifiers and "watch_list" in known.read_only
    assert "watch_cancel" not in known.read_only and "memory_write" in known.notes


# --- The owner's conditions on the real replies ----------------------------------------

# The reply's number in the conversation: the conditions it breaks, with no tool result.
REAL_REPLIES: dict[int, set[str]] = {
    10: {"internal_term", "claims_inability"},
    16: {"broken_markdown"},
    18: {"broken_markdown"},
    24: {"broken_markdown", "claims_inability"},
    31: {"claims_inability"},
    35: {"broken_markdown", "unbacked_claim"},
    37: {"unbacked_claim"},
    43: {"broken_markdown", "unbacked_claim"},
    47: {"unbacked_claim"},
    51: {"language"},
    59: {"internal_term", "broken_markdown"},
    63: {"unbacked_claim"},
    65: {"internal_term", "broken_markdown"},
    69: {"unbacked_claim"},
    71: {"internal_term", "claims_inability"},
    73: {"claims_inability"},
    75: {"internal_term", "claims_inability"},
    77: {"internal_term", "unbacked_claim"},
}


@pytest.mark.parametrize("number", sorted(REAL_REPLIES))
def test_a_real_bad_reply_breaks_the_owners_conditions(number: int):
    assert set(score.conditions(ANY, turn_record(number))) == REAL_REPLIES[number]


def test_the_real_replies_name_what_leaked():
    assert score.conditions(ANY, turn_record(10))["internal_term"] == (
        "broker_account_not_found, symbol_not_found"
    )
    assert score.conditions(ANY, turn_record(65))["internal_term"] == (
        "goals, owner_attention, routines, waiting"
    )
    assert score.conditions(ANY, turn_record(77))["internal_term"] == "watch, watch_cancel"
    assert score.conditions(ANY, turn_record(63))["unbacked_claim"] == "تم, أُزيلت"
    assert score.conditions(ANY, turn_record(69))["unbacked_claim"] == "سأحذف"


@pytest.mark.parametrize("number", [4, 6, 8, 14, 33, 39, 45, 53, 55, 61, 67, 79])
def test_a_real_reply_that_breaks_no_condition_is_left_alone(number: int):
    # Offers ("إذا تريد، ...") and verifications ("تم التحقق") are not claims of an effect.
    assert score.conditions(ANY, turn_record(number)) == {}


GOOD_REPLIES = [
    # The confirmation lines the brief asks for, each with its successful effect.
    ("ضبطت الهدف عند 4052.82 ووقف الخسارة عند 4049.82 على صفقة الذهب.", "trade_execute"),
    ("تم: إذا وصل ربح صفقة الذهب إلى 100 دولار أغلقها فورًا.", "watch_create"),
    ("حذفت المتابعات الثلاث على EURUSDm، ومهمة إدارة الحساب باقية كما هي.", "watch_cancel"),
    ("سأغلق الصفقة تلقائيًا عند ربح 100 دولار، والمتابعة شغّالة الآن.", "watch_create"),
]


@pytest.mark.parametrize(("reply", "tool"), GOOD_REPLIES)
def test_a_confirmation_needs_a_successful_effect_in_the_same_turn(reply: str, tool: str):
    assert score.conditions(ANY, record(reply, [call(tool, status="confirmed")])) == {}
    assert set(score.conditions(ANY, record(reply))) == {"unbacked_claim"}
    # A read, a failed or refused effect, a pending approval and a private note back nothing.
    for unbacked in (
        call("watch_list", watches=[]),
        call(tool, status="failed", code="volume_out_of_range"),
        call(tool, ok=False, code="market_watches_not_found"),
        refused(tool, "market_watches_not_found"),
        call(tool, _runtime_wait=True),
        call("memory_write", id="note"),
        call("wait_for_input", _runtime_wait=True),
    ):
        assert "unbacked_claim" in score.conditions(ANY, record(reply, [unbacked])), unbacked


def test_a_clean_analysis_passes_every_condition():
    reply = (
        "**وضع الذهب الآن: ميل صعودي خفيف.**\n\n"
        "- السعر الحالي: **4049.87 / 4050.11** على XAUUSDm\n"
        "- **15m:** مسطّح\n- **1h:** صاعد نسبيًا\n- **4h:** محايد\n- **1d:** محايد\n\n"
        "**الخلاصة:** انتظار أفضل من شراء فوري. Bid / Ask قريبان من منتصف نطاق اليوم."
    )
    assert score.conditions(ANY, record(reply, [call("market_snapshot", symbol="XAUUSDm")])) == {}


@pytest.mark.parametrize(
    ("reply", "condition"),
    [
        ("الحالة: confirmed والتحقق تم.", "internal_term"),
        ("ما لقيت أي routines عندك.", "internal_term"),
        ("رجع الوسيط broker_rate_limited، جرّب بعد قليل.", "internal_term"),
        ("استخدمت trade_execute لفتح الصفقة.", "internal_term"),
        ("المتابعة رقم 0b9f0da6-ab6b-5bd7-851b-545d71d5cb06 ما زالت موجودة.", "private"),
        ("السبريد ** 0.24** الآن.", "broken_markdown"),
        ("**الخلاصة العملية: ** انتظار.", "broken_markdown"),
        ("- **هدف الربح:****+2 USD** تقريبًا", "broken_markdown"),
        ("الوضع **غير محسوم", "broken_markdown"),
        ("لا يمكنني حذف المتابعات من هنا.", "claims_inability"),
        ("ما عندي أداة لإلغاء المتابعة.", "claims_inability"),
        ("I can't cancel watches from this conversation.", "claims_inability"),
        ("Bu cümle eksik. İstersen Türkçe devam edebilirim.", "language"),
        ("Gold is flat on the hourly chart and I would wait for a breakout.", "language"),
        ("مراقب. إذا وصل لهذا المستوى أغلقه فورًا.", "unbacked_claim"),
        ("أراقب **XAUUSDm** على حسابك.", "unbacked_claim"),
        ("Done. I closed the position.", "unbacked_claim"),
    ],
)
def test_each_condition_catches_its_bad_reply(reply: str, condition: str):
    assert condition in score.conditions(ANY, record(reply))


@pytest.mark.parametrize(
    "reply",
    [
        "السعر الآن **4049.87 / 4050.11** والسبريد **0.24**.",
        "القراءة تميل إلى**انتظار** أكثر من شراء فوري.",
        "- **15m:** مسطّح\n* **1h:** صاعد",
        "الرمز الصحيح هنا هو `XAUUSDm` وليس `XAUUSD`.",
        "تم التحقق: المركز ما زال مفتوحًا، والربح الآن +0.56 USD.",
        "إذا تريد، أتابعه لك حتى يصل للهدف.",
        "أقدر أتابع متابعات السوق وألخص التغيّر.",
        "لم أفهم الجملة الأخيرة.",
        "الحساب: Exness-MT5Trial16، والمركز شراء XAUUSDm بحجم 0.01. Stop Loss غير مضبوط.",
    ],
)
def test_a_good_reply_is_not_rejected(reply: str):
    assert score.conditions(ANY, record(reply)) == {}


# From the adversarial review of the scorer: replies written to slip through it.
SLIPPERY: dict[str, list[str]] = {
    "unbacked_claim": [
        "ألغيتها.",
        "حذفتها كلها.",
        "سكّرتها.",
        "قمت بإلغاء المتابعة.",
        "مسحت المتابعات الثلاث.",
        "حطّيت ستوب على 2400.",
        "خلصت، المتابعة انحذفت.",
        "حذفت المتابعة، إذا تريد أراجع الباقي.",
        "رح أتابع السعر وأخبرك.",
        "أراقب السوق الآن.",
        "بخبرك لما يوصل 2400.",
        "سيتم تنبيهك عند 2400.",
        "أنا متابع الصفقة وببلغك.",
        "عم راقب السعر هلق.",
        "سأبقيه تحت المراقبة.",
        "The watch has been cancelled.",
        "Cancelled. Nothing is being watched now.",
        "I just cancelled it.",
        "I am watching it.",
        "You'll get an alert at 2400.",
    ],
    "claims_inability": [
        "ليس لدي صلاحية الوصول إلى المتابعات.",
        "ما فيني ألغي المتابعة.",
        "مابقدر احذفها.",
        "مو قادر أوصل للمتابعات.",
        "تعذّر عليّ إلغاء المتابعة.",
        "لست قادراً على حذفها.",
        "هذه الخاصية غير متاحة لي.",
        "هذا خارج قدراتي حالياً.",
        "لا تتوفر لدي أداة للإلغاء.",
        "I'm not able to cancel it.",
        "That's not something I can do.",
    ],
    "internal_term": [
        "الحالة: **Waiting**",
        "الخطأ WATCH_NOT_FOUND.",
        "الخطأ: `watch_not_found`",
        "استعملت watchCancel.",
        "الطلب pending_approval.",
        "حالة المهمة: waiting_for_input",
    ],
    "broken_markdown": ["**السعر:**2400", "**«السعر»**هو 2400"],
    "language": [
        "The Price Is Now 2400 And Rising.",
        "Цена сейчас 2400.",
        "`The price is 2400 and the trend is up.`",
    ],
}


@pytest.mark.parametrize(
    ("condition", "reply"),
    [(name, reply) for name, replies in SLIPPERY.items() for reply in replies],
)
def test_a_reply_written_to_slip_through_is_caught(condition: str, reply: str):
    read = [call("watch_list", watches=[])]
    assert condition in score.conditions(ANY, record(reply, read))


# And good replies written to be rejected: each of them only read the account.
HONEST = [
    "خلال ساعات التداول السعر 2400.",
    "السوق يفتح بعد ساعتين.",
    "سابقاً كان السعر 2300.",
    "سنوات من البيانات تقول ذلك.",
    "سألتني عن الذهب: السعر 2400.",
    "سأنتظر تأكيدك قبل التنفيذ.",
    "سأحتاج رقم الصفقة لأكمل.",
    "آخر صفقة تم فتحها أمس الساعة 10.",
    "تم العثور على ثلاث متابعات.",
    "ما تم شيء لسا.",
    "ما حذفت شيئاً بعد، أنتظر تأكيدك.",
    "هل تم إغلاق الصفقة من طرفك؟",
    "هل أراقبها لك؟",
    "لا أستطيع ضمان الربح.",
    "السعر ما قدر يكسر المقاومة.",
    "إذا ما قدرت توصل للمنصة خبرني.",
    "ما قدرت أفهم قصدك، ممكن توضح؟",
    "قلتَ: «حذفت المتابعة»، لكن ما زالت موجودة.",
    "مراقب المخاطر يمنع ذلك.",
    "الـStop Loss عند 2400 والـTake Profit عند 2450 على صفقة الذهب.",
    "السعر**2400**دولار",
    "افتح الـchart وشوف.",
    "الصفقة بوقف خسارة 4049.82 وهدف 4052.82.",
    "المتابعات الثلاث ما زالت موجودة.",
    "تماماً، هذا هو المقصود.",
    "الاتجاه على H1 صاعد وعلى M15 محايد، وRSI عند 46.",
]


@pytest.mark.parametrize("reply", HONEST)
def test_an_honest_reply_written_to_be_rejected_passes(reply: str):
    assert score.conditions(ANY, record(reply, [call("watch_list", watches=[])])) == {}


def test_only_a_settled_effect_backs_a_claim():
    reply = "فتحت الصفقة."
    for unsettled in ("submitted", "reserved", "pending", "rejected", "failed", "ambiguous"):
        turn = record(reply, [call("trade_execute", status=unsettled)])
        assert "unbacked_claim" in score.conditions(ANY, turn), unsettled
    assert "unbacked_claim" in score.conditions(ANY, record(reply, [call("owner_action_propose")]))
    assert score.conditions(ANY, record(reply, [call("trade_execute", status="confirmed")])) == {}


def test_an_english_owner_may_read_ordinary_english_words():
    english = {**ANY, "language": "en"}
    assert score.conditions(english, record("The order is still pending; I am waiting.")) == {}
    assert "internal_term" in score.conditions(english, record("Task is in owner_attention."))


def test_the_question_card_is_part_of_what_the_owner_sees():
    asked = call(
        "wait_for_input",
        {"question": "أي حالة تريد أن أعرضها لك؟", "choices": [{"label": "waiting"}]},
    )
    found = score.conditions(ANY, record("", [asked], status="waiting_input"))
    assert found == {"internal_term": "waiting"}


def test_rounds_are_bounded():
    assert "rounds" in score.conditions(ANY, record("مرحبًا.", rounds=score.MAX_ROUNDS + 1))
    assert score.conditions({**ANY, "max_rounds": 12}, record("مرحبًا.", rounds=12)) == {}


def test_inability_is_judged_only_when_a_serving_tool_is_registered():
    reply = "لا أستطيع إرسال فاكس."
    assert "claims_inability" in score.conditions(ANY, record(reply))
    assert score.conditions({"tools": ["fax_send"], "expect": []}, record(reply)) == {}


# --- The expectation checks ----------------------------------------------------------------


def test_patterns_match_numbers_choices_lengths_and_text():
    assert score.matches("4052.82", {"near": 4052.819})
    assert not score.matches("4052.9", {"near": 4052.82})
    assert not score.matches(None, {"near": 1}) and not score.matches("abc", {"near": 1})
    assert score.matches("cross_above", {"in": ["above", "cross_above"]})
    assert score.matches({"watches": [1, 2, 3]}, {"watches": {"length": 3}})
    assert score.matches({"tools": [{"name": "watch_cancel"}]}, {"contains": "watch_cancel"})
    assert score.matches({"a": {"b": 0.01}, "c": 1}, {"a": {"b": "0.01"}})
    assert not score.matches({"enabled": "true"}, {"enabled": True})
    assert not score.matches("x", {"a": 1})


def test_call_order_state_card_and_reply_checks():
    cancel = call("watch_cancel", {"watch_id": "w1"}, id="w1")
    listed = call("watch_list", watches=[])
    turn = record(
        "حذفت المتابعات الثلاث.",
        [refused("watch_cancel", "market_watches_not_found"), cancel, listed],
        state_after={
            "positions": [{"symbol": "XAUUSDm", "volume": 0.01, "takeProfit": 4052.82}],
            "watches": [{"code": "watch_cancelled", "enabled": False}],
            "tasks": [],
            "orders": [],
        },
    )
    assert score.holds({"call": "watch_cancel"}, turn)
    assert not score.holds({"call": "watch_cancel", "times": 2}, turn)
    assert score.holds({"call": "watch_cancel", "ok": False}, turn)
    assert score.holds({"call": ["watch_pause", "watch_cancel"], "with": {"watch_id": "w1"}}, turn)
    assert score.holds({"call": "watch_cancel", "result": {"id": "w1"}}, turn)
    assert score.holds({"no_call": "watch_create"}, turn)
    assert not score.holds({"no_call": "watch_list"}, turn)
    assert score.holds({"after": ["watch_cancel", "watch_list"]}, turn)
    assert not score.holds({"after": ["watch_list", "watch_cancel"]}, turn)
    assert score.holds({"state": "watches", "where": {"enabled": True}, "count": 0}, turn)
    assert score.holds({"state": "positions", "where": {"takeProfit": {"near": 4052.82}}}, turn)
    assert score.holds({"reply": "lines", "max": 1}, turn)
    assert score.holds({"reply": "no_question"}, turn)
    assert score.holds({"reply": "mentions", "words": ["المتابعات"]}, turn)
    assert not score.holds({"reply": "states_volume"}, turn)
    assert score.holds({"reply": "states_volume"}, {**turn, "replies": ["اشتريت 0.01 لوت."]})
    assert not score.holds({"reply": "states_volume"}, {**turn, "replies": ["اشتريت 10.01"]})
    assert score.holds({"any": [[{"call": "trade_execute"}], [{"call": "watch_list"}]]}, turn)
    assert not score.holds({"any": [[{"call": "trade_execute"}], [{"status": "failed"}]]}, turn)
    question = {"question": "أي خطة؟", "choices": [{"label": "10 × 0.01"}]}
    card = record(
        "", [call("wait_for_input", question, _runtime_wait=True)], status="waiting_input"
    )
    assert score.holds({"card": {"numbers": True}}, card)
    assert not score.holds({"card": {"mentions": ["XAUUSDm"]}}, card)
    assert not score.holds({"reply": "no_question"}, card)
    assert not score.holds({"reply": "lines", "max": 1}, card)
    assert score.holds({"waits": "wait_for_input"}, card)
    assert not score.holds({"card": {}}, turn)


def test_a_long_or_second_line_is_not_one_confirmation_line():
    assert not score.holds({"reply": "lines", "max": 1}, record("تم.\nوالمركز مفتوح."))
    assert not score.holds({"reply": "lines", "max": 1}, record("ت" * (score.LINE_CHARS + 1)))


def test_a_probe_is_held_to_calls_and_state_only():
    checks = SCENARIOS["M68"]["expect"]
    kept = [score.check_name(check) for check in score.structural(checks)]
    assert "reply:lines" not in kept and "call:watch_cancel" in kept
    resumed = score.structural(SCENARIOS["M78"]["expect"])
    assert [len(check["any"]) for check in resumed] == [1]  # the reply option is dropped
    assert score.structural(SCENARIOS["M30"]["expect"])[0]["any"] == [
        [{"call": "trade_execute", "with": {"action": "buy"}}]
    ]


# --- Whole turns: what the owner asked for, and what he got --------------------------------


def good_turn(name: str) -> dict[str, Any]:
    position = {
        "id": "2217873130",
        "symbol": "XAUUSDm",
        "type": "POSITION_TYPE_BUY",
        "volume": 0.01,
    }
    if name == "M34":
        arguments = {"action": "modify_position", "take_profit": "4052.82", "stop_loss": 4049.819}
        return record(
            "ضبطت الهدف عند 4052.82 ووقف الخسارة عند 4049.82 على صفقة الذهب.",
            [call("trade_execute", arguments, status="confirmed")],
            state_after={"positions": [{**position, "takeProfit": 4052.82, "stopLoss": 4049.82}]},
        )
    if name == "M40":
        watch = {"kind": "position", "metric": "profit", "condition": "above", "level": "100"}
        return record(
            "تم: إذا وصل ربح صفقة الذهب إلى 100 دولار أغلقها فورًا.",
            [call("watch_create", watch, id="w")],
            state_after={"positions": [position], "watches": [{**watch, "enabled": True}]},
        )
    cancelled = [call("watch_cancel", {"watch_id": str(n)}, id=str(n)) for n in range(3)]
    return record(
        "حذفت المتابعات الثلاث، ومهمة إدارة الحساب باقية.",
        [call("watch_list", watches=[1, 2, 3]), *cancelled, call("watch_list", watches=[])],
        state_after={
            "watches": [{"code": "watch_cancelled", "enabled": False}] * 3,
            "tasks": [{"title": "إدارة حساب التداول", "status": "waiting"}],
        },
    )


@pytest.mark.parametrize("name", ["M34", "M40", "M68"])
def test_the_outcome_the_owner_asked_for_passes(name: str):
    assert score.judge(SCENARIOS[name], good_turn(name)) == []


def test_what_the_owner_got_fails_the_same_scenarios():
    position = {
        "id": "2217873130",
        "symbol": "XAUUSDm",
        "type": "POSITION_TYPE_BUY",
        "volume": 0.01,
    }
    untouched = {"positions": [position], "watches": [], "tasks": []}
    assert score.judge(SCENARIOS["M34"], turn_record(35) | {"state_after": untouched}) == [
        "broken_markdown",
        "call:trade_execute",
        "reply:lines",
        "state:positions",
        "unbacked_claim",
    ]
    assert score.judge(SCENARIOS["M40"], turn_record(41) | {"state_after": untouched}) == [
        "broken_markdown",
        "close_at_100_armed",
        "reply:lines",
    ]
    three = {"watches": [{"enabled": True, "code": None}] * 3, "tasks": [], "positions": []}
    assert score.judge(SCENARIOS["M68"], turn_record(69) | {"state_after": three}) == [
        "call:watch_cancel",
        "order:watch_cancel>watch_list",
        "state:all_watches_cancelled",
        "unbacked_claim",
    ]
    # [77]: a new disabled watch "as a trial" instead of the deletion.
    trial = [call("watch_create", {"enabled": False}, id="w4")]
    assert "no_trial_resource" in score.judge(
        SCENARIOS["M76"], turn_record(77, trial) | {"state_after": three}
    )
    # A close before the condition holds is not a standing condition.
    closed = record("تم سكره.", [call("trade_execute", {"action": "close_position"})])
    assert score.judge(
        SCENARIOS["M40"], closed | {"state_after": {"positions": [], "watches": []}}
    ) == [
        "close_at_100_armed",
        "state:position_still_open",
    ]


# --- The fake MetaApi terminal under the real adapter --------------------------------------


def adapter(terminal: broker.FakeTerminal) -> broker.FakeMetaApiBroker:
    broker.FakeMetaApiBroker.terminals[terminal.account_id] = terminal
    return broker.FakeMetaApiBroker(terminal.account_id, None, "no-key", "connection")


async def code_of(awaitable: Any) -> tuple[str, int]:
    with pytest.raises(LonoraError) as raised:
        await awaitable
    return raised.value.code, raised.value.status


@pytest.mark.parametrize(
    ("variant", "gold"),
    [("m", "XAUUSDm"), ("c", "XAUUSDc"), ("pro", "XAUUSD.pro"), ("gold", "GOLD")],
)
@pytest.mark.asyncio
async def test_each_account_naming_reads_like_the_owners_broker(variant: Any, gold: str):
    fake = adapter(broker.FakeTerminal(variant=variant))
    symbols = await fake.symbols()
    assert gold in symbols and len(symbols) == len(broker.MARKETS)
    assert "XAUUSD" not in symbols
    instrument = await fake.instrument(gold)
    assert (instrument.contract_size, str(instrument.volume_min), instrument.digits) == (
        100,
        "0.01",
        3,
    )
    quote = await fake.quote(gold)
    assert (str(quote.bid), str(quote.ask)) == ("4049.87", "4050.11")
    assert quote.profit_tick_value == instrument.tick_size * 100
    for timeframe in broker.TIMEFRAMES:
        candles = await fake.candles(gold, timeframe, 50)
        assert len(candles) == 50 and candles[-1].close == quote.bid
        assert all(candle.low <= min(candle.open, candle.close) for candle in candles)
        assert all(
            earlier.time < later.time for earlier, later in zip(candles, candles[1:], strict=False)
        )
        assert candles == await fake.candles(gold, timeframe, 50)  # the same history every time
    account = await fake.account()
    assert (account.server, account.currency, account.balance) == (
        "Exness-MT5Trial16",
        "USD",
        10000,
    )


@pytest.mark.asyncio
async def test_positions_orders_modify_and_close_through_the_real_adapter():
    terminal = broker.FakeTerminal()
    fake = adapter(terminal)

    def request(action: str, **fields: Any) -> TradeRequest:
        return TradeRequest.model_validate(
            {"account_id": "connection", "symbol": "XAUUSDm", "action": action, **fields}
        )

    bought = await fake.execute(request("buy", volume="0.01"))
    assert bought.status == "confirmed" and bought.details["price"] == 4050.11
    assert (await fake.reconcile(bought.operation_id)).status == "confirmed"
    position = (await fake.positions())[0]
    assert (position.id, position.side, str(position.profit)) == (bought.broker_id, "buy", "-0.24")
    # The owner's plan of [34]: +2 USD and -1 USD on 0.01 lot of a 100-ounce contract.
    terminal.positions[0]["openPrice"] = 4050.819
    terminal.bids["XAUUSDm"] = broker.Decimal("4052.819")
    assert str((await fake.positions())[0].profit) == "2.0"
    terminal.bids["XAUUSDm"] = broker.Decimal("4051.792")
    levels = {"take_profit": "4052.82", "stop_loss": "4049.82"}
    modified = await fake.execute(request("modify_position", position_id=position.id, **levels))
    assert modified.status == "confirmed"
    position = (await fake.positions())[0]
    assert (str(position.take_profit), str(position.stop_loss)) == ("4052.82", "4049.82")
    pending = await fake.execute(request("buy_limit", volume="0.02", price="4040"))
    assert [order.id for order in await fake.orders()] == [pending.broker_id]
    assert (
        await fake.execute(request("cancel_order", order_id=pending.broker_id))
    ).status == "confirmed"
    assert await fake.orders() == []
    closed = await fake.execute(request("close_position", position_id=position.id))
    assert closed.status == "confirmed" and await fake.positions() == []
    assert terminal.state()["closed_positions"] == [position.id]
    assert (await fake.account()).balance == broker.Decimal("10000.97")


@pytest.mark.asyncio
async def test_the_terminal_refuses_like_a_broker():
    terminal = broker.FakeTerminal()
    fake = adapter(terminal)

    def buy(**fields: Any) -> TradeRequest:
        return TradeRequest(account_id="connection", symbol="XAUUSDm", action="buy", **fields)

    small = await fake.execute(buy(volume="0.001"))
    assert (small.status, small.code) == ("failed", "TRADE_RETCODE_INVALID")
    wrong_side = await fake.execute(buy(volume="0.01", stop_loss="4060"))
    assert (wrong_side.status, wrong_side.code) == ("failed", "TRADE_RETCODE_INVALID_STOPS")
    assert terminal.positions == []
    # An unknown symbol is the provider's 404, on every read.
    for read in (fake.instrument("XAUUSD"), fake.quote("XAUUSD"), fake.candles("XAUUSD", "1h", 5)):
        assert (await code_of(read))[1] == 404
    # A rate limit, then a connection that drops in the middle of the turn and comes back.
    terminal.fail("rate_limit")
    assert await code_of(fake.quote("XAUUSDm")) == ("broker_rate_limited", 429)
    terminal.fail("connection_drop", after=2, times=1)
    await fake.quote("XAUUSDm")
    await fake.positions()
    assert await code_of(fake.account()) == ("broker_connection_unavailable", 502)
    assert (await fake.account()).currency == "USD"
    # An account the provider does not know.
    terminal.known = False
    assert await code_of(fake.account()) == ("broker_account_not_found", 404)


@pytest.mark.xfail(strict=True, reason="main reports a symbol's 404 as an unknown account ([10])")
@pytest.mark.asyncio
async def test_an_unknown_symbol_is_not_reported_as_an_unknown_account():
    fake = adapter(broker.FakeTerminal())
    assert (await code_of(fake.instrument("XAUUSD")))[0] == "symbol_not_found"
    assert (await code_of(fake.quote("XAUUSD")))[0] == "symbol_not_found"


def test_only_a_registered_fake_account_is_ever_connected():
    with broker.installed(broker.FakeTerminal(account_id="known")):
        import lonora_adapters.brokers.metaapi as metaapi
        import lonora_trading.connections as connections

        assert metaapi.MetaApiBroker is connections.MetaApiBroker is broker.FakeMetaApiBroker
        connected = metaapi.MetaApiBroker("known", None, "no-key")
        assert isinstance(connected, broker.FakeMetaApiBroker)
        assert connected.terminal.account_id == "known"
        with pytest.raises(LonoraError, match="agent_eval_account_not_faked"):
            metaapi.MetaApiBroker("a-real-account-id", None, "a-real-token")
    assert "known" not in broker.FakeMetaApiBroker.terminals


# --- The bank -----------------------------------------------------------------------------

# Every problem message of OWNER_BRIEF §2 and §8, by its number in the conversation.
PROBLEM_TURNS = [1, 9, 11, 13, 15, 17, 23, 28, 30, 34, 36, 38, 40, 42, 46] + [
    48,
    50,
    52,
    54,
    56,
    58,
    62,
    64,
    68,
    70,
    72,
    74,
    76,
    78,
    80,
]
EXTRA = ["X_c", "X_pro", "X_gold", "X_code", "X_alias", "X_unknown", "X_drop", "X_rate"] + [
    "X_args",
    "X_permission",
]


def test_every_problem_message_is_a_scenario_in_the_owners_own_words():
    source = json.loads(bank.SCENARIOS.read_text())["scenarios"]
    assert len(source) == len({item["id"] for item in source}) == len(SCENARIOS) == 40
    by_turn = {item["turn"]: item for item in source if "turn" in item}
    assert sorted(by_turn) == PROBLEM_TURNS
    assert [item["id"] for item in source if "turn" not in item] == EXTRA
    for number, item in by_turn.items():
        turn, scenario = TURNS[number], SCENARIOS[item["id"]]
        assert turn["role"] == "user" and "message" not in item
        assert item["source"].startswith(f"[{number}]→[{number + 1}]")
        assert scenario["message"] == item.get("voice", {}).get("heard", turn["content"])
        assert [m["content"] for m in scenario["state"]["history"]] == [
            earlier["content"]
            for earlier in TURNS.values()
            if earlier["n"] < number and earlier["role"] in {"user", "assistant"}
        ]
    # The words the brief quotes, exactly as the owner typed them.
    assert SCENARIOS["M09"]["message"] == "طيب شو وضع الذهب"
    assert SCENARIOS["M40"]["message"] == "راقبه بس صار ربح 100 دولار سكره"
    assert SCENARIOS["M68"]["message"] == "احذف كل المتابعات والمهام الفرعية فقط"
    assert SCENARIOS["M76"]["message"] == "جرب" and SCENARIOS["M11"]["message"] == "ضع حرف m"


def test_every_scenario_is_runnable_and_scorable():
    registered = set(load_tools().tools)
    empty = record("", status="completed")
    for scenario in SCENARIOS.values():
        assert scenario["title"] and scenario["group"] in "ABCDEFG"
        # No tool serves a size below the contract minimum: declining it is no false inability.
        assert scenario["tools"] or scenario["id"] == "X_args"
        assert set(scenario["tools"]) <= registered, scenario["id"]
        assert scenario["expect"] or scenario["id"] == "G01", scenario["id"]
        checks = [*scenario["expect"], *scenario.get("probe", {}).get("expect", [])]
        for check in checks:
            score.holds(check, empty)  # an unknown kind of check raises
            named = [check[kind] for kind in ("call", "no_call", "waits") if kind in check]
            assert {tool for item in named for tool in score.names(item)} <= registered
        assert len({score.check_name(check) for check in scenario["expect"]}) == len(
            scenario["expect"]
        ), scenario["id"]
        for step in scenario.get("probe", {}).get("calls", []):
            assert step["tool"] in registered
        assert "$" not in json.dumps([scenario["expect"], scenario["state"]], ensure_ascii=False)
        terminal = bank.terminal(scenario)
        assert len(terminal.positions) == len(scenario["state"].get("positions", []))
        for fault in scenario["state"].get("faults", []):
            assert fault["kind"] in {"rate_limit", "connection_drop", "account_not_found"}


def test_the_extra_scenarios_cover_section_8():
    gold = {name: SCENARIOS[name]["expect"][0]["result"]["symbol"] for name in EXTRA[:5]}
    assert gold == {
        "X_c": "XAUUSDc",
        "X_pro": "XAUUSD.pro",
        "X_gold": "GOLD",
        "X_code": "XAUUSDm",
        "X_alias": "XAUUSDm",
    }
    assert "الذهب" in SCENARIOS["X_gold"]["message"]
    assert "card" in SCENARIOS["X_unknown"]["expect"][0]
    assert SCENARIOS["X_drop"]["state"]["faults"][0]["kind"] == "connection_drop"
    assert SCENARIOS["X_rate"]["state"]["faults"][0]["kind"] == "rate_limit"
    assert SCENARIOS["X_permission"]["state"]["mandate"] == "none"
    assert SCENARIOS["M09"]["state"].get("mandate", "full") == "full"
    # The position of [26] is open in every later scenario; the watches of [59] from [56] on.
    assert all(
        SCENARIOS[f"M{n}"]["state"]["positions"][0]["price"] == "4050.819"
        for n in PROBLEM_TURNS
        if n > 26
    )
    assert all(len(SCENARIOS[f"M{n}"]["state"]["watches"]) >= 3 for n in PROBLEM_TURNS if n >= 56)


# --- The baseline: recorded on main, replayed and held strictly ----------------------------


def test_the_recorded_baseline_still_scores_exactly_as_listed():
    live = BASELINE["live"]
    records = score.load_records(bank.FIXTURES / live["recording"])
    assert set(records) == set(SCENARIOS) == set(live["expected"])
    assert {item["model"] for item in records.values()} == {live["model"]}
    scored = {name: score.judge(SCENARIOS[name], item) for name, item in records.items()}
    changed = {name: found for name, found in scored.items() if found != live["expected"][name]}
    assert not changed, f"{STALE}: {json.dumps(changed, ensure_ascii=False)}"


def test_the_structural_probes_still_answer_exactly_as_listed():
    url = make_url(os.environ.get("LONORA_DATABASE_URL") or "sqlite://")
    if not url.drivername.startswith("postgresql"):
        pytest.skip("the structural probes need a disposable PostgreSQL (LONORA_DATABASE_URL)")
    # A database of its own, in a process of its own: the probes migrate, seed and drop it.
    own = url.set(database=f"agent_eval_{uuid4().hex[:10]}_test")
    environment = {**os.environ, "LONORA_DATABASE_URL": own.render_as_string(hide_password=False)}
    done = subprocess.run(
        [sys.executable, str(ROOT / "scripts/agent_eval/run.py"), "--probe", "--json"],
        env=environment,
        capture_output=True,
        text=True,
        timeout=600,
    )
    assert done.returncode == 0, done.stderr[-2000:]
    scored = json.loads(done.stdout[done.stdout.index("{") :])
    expected = BASELINE["structural"]["expected"]
    assert set(scored) == {name for name, item in SCENARIOS.items() if "probe" in item}
    changed = {name: found for name, found in scored.items() if found != expected.get(name)}
    assert not changed, f"{STALE}: {json.dumps(changed, ensure_ascii=False)}"
