"""Deterministic reply guards keyed on the owner's own words and this request's results.

- ``request_refusal``: a request to stop, pause or resume trading is never answered with a
  new entry, nor a limit to adopt with a memory note. The call is refused before its handler runs, so no approval card appears, and
  the result names the owner controls that do answer it.
- ``claim_gate``: a final reply may say an action happened only when a successful
  effect result in this request supports it. One repair turn, then an honest line.
- ``code_deliverable``: D5, Lonora hands the owner no code as a product. Q36 keeps a
  short fenced block as explanation.

The patterns are guards on a narrow set of phrasings, never request routers.
"""

import json
import re
from collections.abc import Collection
from dataclasses import dataclass
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage, ToolCall

from .context.financial_result import FINANCIAL_CALLS
from .runtime_notices import is_owner_message, is_runtime_notice, prefers_arabic

_STATE_KEY = "effect_claim_gate"
# Entries and pending-entry edits: the class a no_new_entries restriction refuses.
ENTRY_ACTIONS = frozenset(
    {"buy", "sell", "buy_limit", "sell_limit", "buy_stop", "sell_stop", "modify_order"}
)
# A fenced block of at least this many lines answering a request for code is a deliverable.
DELIVERABLE_LINES = 8


def _normalized(text: str) -> str:
    """Arabic without diacritics or tatweel, one alef, yaa and haa form; lower-case Latin."""
    text = re.sub(r"[ً-ٰٟـ]", "", text)
    text = re.sub(r"[أإآٱ]", "ا", text).replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[ؤئ]", "ء", text)
    return text.lower()


def owner_words(messages: list[ModelMessage]) -> str:
    """The latest owner message: the request this reply answers."""
    return next((m.content for m in reversed(messages) if is_owner_message(m)), "")


_STOP = [
    re.compile(
        r"(?:وقف|ايقاف|علق|تعليق|جمد|تجميد)\S*\s+(?!(?:ال)?خساره)(?:\S+\s+){0,2}?"
        r"(?:ال)?(?:تداول|صفق|تنفيذ|دخول|شراء|بيع)"
    ),
    re.compile(r"\bلا\s+(?:ت|ن)?(?:فتح|تداول|دخل)"),
    re.compile(r"(?:بدون|بلا|ممنوع)\s+(?:ال)?(?:صفقات|صفقه|تداول|دخول)"),
    re.compile(
        r"\b(?:stop|pause|halt|suspend|freeze)\b(?!\W*loss)\W+(?:\w+\W+){0,3}?"
        r"(?:trading|trades?|entries|positions|opening|buying|selling)\b"
    ),
    re.compile(r"\bno\s+(?:new|more)\s+(?:trades?|positions|entries)\b"),
    re.compile(r"\b(?:don'?t|do\s+not)\s+(?:open|trade|enter)\b"),
]


_RESUME = [
    re.compile(r"(?:استانف|استءناف|شغل|تشغيل|فعل|تفعيل|رجع|ارجاع)\S*\s+(?:ال)?تداول"),
    re.compile(r"\b(?:resume|unpause|restart|re-?enable|turn\s+on)\b\W+(?:\w+\W+){0,2}?trading\b"),
]


# "Don't stop trading" / «لا توقف الصفقات» negate the stop verb itself.
_NEGATED_STOP = re.compile(
    r"\b(?:don'?t|do\s+not|never)\s+(?:stop|pause|halt|suspend|freeze)\b|"
    r"(?:^|\s)(?:لا|ما|لن|مو)\s+\S*(?:وقف|علق|جمد)\S*"
)


def stop_requested(text: str) -> bool:
    plain = _NEGATED_STOP.sub(" ", _normalized(text))
    return any(pattern.search(plain) for pattern in _STOP)


def resume_requested(text: str) -> bool:
    plain = _normalized(text)
    return any(pattern.search(plain) for pattern in _RESUME)


_CANCEL_REQUEST = re.compile(r"\bالغ(?:ي|اء)?\b|\bاحذف|\bامسح|\b(?:cancel|delete|remove)\b")
_MODEL_REQUEST = re.compile(r"نموذج|موديل|\b(?:model|llm)\b")


def requested_tools(messages: list[ModelMessage]) -> list[str]:
    """Owner-control tools the owner's words call for, offered natively for this Run.

    Presentation only: they join the promoted set within its budget, and execution
    still validates every call (G0: the model reached for the native trade tool).
    """
    words = owner_words(messages)
    plain = _normalized(words)
    names: list[str] = []
    if stop_requested(words):
        names.append("trade_restriction_create")
    if _CANCEL_REQUEST.search(plain):
        names += ["watch_list", "watch_cancel"]
    if _MODEL_REQUEST.search(plain):
        names += ["model_list", "model_request"]
    return names


def _in_claim_repair(messages: list[ModelMessage]) -> bool:
    """Whether the claim gate's repair notice was given in the current owner request."""
    for message in reversed(messages):
        if is_owner_message(message):
            return False
        if is_runtime_notice(message) and '"kind": "effect_claim_check"' in message.content:
            return True
    return False


def request_refusal(messages: list[ModelMessage], call: ToolCall) -> dict[str, Any] | None:
    """The refused result of a call that cannot answer the owner's control request:
    a new entry for a stop, pause or resume, a memory note for a limit to adopt, a
    financial call in the claim gate's repair turn."""
    if call.name in FINANCIAL_CALLS and _in_claim_repair(messages):
        return {
            "ok": False,
            "code": "claim_repair_no_financial_call",
            "executed": False,
            "message": "This turn only corrects a reply that claimed an action; it cannot "
            "place, change or close a trade, and nothing was sent. Tell the owner plainly "
            "what has not been done.",
        }
    if call.name == "memory_write" and _LIMIT_SET.search(_normalized(owner_words(messages))):
        return {
            "ok": False,
            "code": "owner_limit_request_not_memory",
            "executed": False,
            "message": "The owner asked to adopt a limit; memory enforces nothing and was not "
            "changed. Propose it with owner_action_propose kind set_account_limits (through "
            "tool_call) now; once it is proposed, the card waits for the owner's tap.",
        }
    entry = call.name == "goal_step_execute" or (
        call.name == "trade_execute" and call.arguments.get("action") in ENTRY_ACTIONS
    )
    if not entry:
        return None
    words = owner_words(messages)
    if stop_requested(words):
        return {
            "ok": False,
            "code": "owner_stop_request_no_entry",
            "executed": False,
            "message": "The owner asked to stop or pause trading; a new entry is never the "
            "answer and nothing was sent. Record the pause with trade_restriction_create "
            "(no_new_entries; valid_until for a time limit such as today), or tell the owner "
            "that Stop new trading is their own control. Closing and protecting positions "
            "stay possible.",
        }
    if resume_requested(words):
        return {
            "ok": False,
            "code": "owner_control_request_no_entry",
            "executed": False,
            "message": "The owner asked to resume trading, not to trade; a new entry is never "
            "the answer and nothing was sent. Only the owner resumes trading: propose it with "
            "owner_action_propose kind resume_trading now; once it is proposed, the card "
            "waits for their tap.",
        }
    return None


_AR_CLAIM_VERBS = (
    "الغيت|لغيت|استانفت|اوقفت|وقفت|حفظت|عدلت|غيرت|انشات|انشءت|فعلت|شغلت|ضبطت|سجلت|"
    "اضفت|حذفت|ازلت|ارسلت|جدولت|اعتمدت|ثبتت|نقلت|طبقت|قمت"
)
_EN_CLAIM_VERBS = (
    "cancel+ed|saved|set|created|updated|changed|paused|resumed|stopped|scheduled|removed|"
    "deleted|enabled|disabled|added|adjusted|moved|switched|recorded|logged|placed|applied"
)
_START = r"(?:^|[\n.!؟?:،;]\s*)"
_CLAIMS = [
    # «تم.» standing alone, or «تم» with the effect it names.
    re.compile(
        _START + r"تم+(?:\s*(?:[.!،,✅]|$)|\s+(?:ال)?(?:حفظ|الغاء|تعديل|ضبط|تفعيل|"
        r"ايقاف|استءناف|انشاء|جدوله|اعتماد|تحديد|تسجيل|ارسال|حذف|تغيير))"
    ),
    re.compile(_START + r"(?:[وف])?(?:لقد\s+|قد\s+)?(?:" + _AR_CLAIM_VERBS + r")(?:ه|ها|هم)?\b"),
    re.compile(_START + r"(?:done|all set)\b"),
    re.compile(
        r"\bi(?:'ve|\s+have)\s+(?:now\s+|just\s+|already\s+)?(?:" + _EN_CLAIM_VERBS + r")\b"
    ),
    # A bare past participle opening a sentence ("Cancelled the alert."); "set" and
    # other forms an imperative shares stay out.
    re.compile(
        _START + r"(?:cancel+ed|saved|created|updated|changed|paused|resumed|stopped|"
        r"scheduled|removed|deleted|enabled|disabled|added|switched)\s+(?:the|your|it)\b"
    ),
]


# Claims of a kind only that kind of tool supports. A cancellation needs a tool that
# cancels (G0 J05: watch_create, then «تم الإلغاء»); a card the owner taps needs a tool
# that raises one (probe: «البطاقة بانتظار لمستك» with no card proposed).
_KINDS = [
    (
        re.compile(r"الغيت|لغيت|حذفت|ازلت|تم\s+(?:ال)?(?:الغاء|حذف)|cancel+ed|removed|deleted"),
        re.compile(r"cancel|delete|remove|revoke|close|lift"),
    ),
    (
        re.compile(
            r"(?:بانتظار|تنتظر|ينتظر)\s+(?:\S+\s+)?(?:لمس|نقر|موافق|توقيع|تاكيد)|"
            r"\bwait(?:s|ing)\b.{0,30}\b(?:tap|approval|confirmation|signature)\b"
        ),
        re.compile(r"owner_action_propose|model_request|agent_create"),
    ),
]


def claims_effect(text: str) -> bool:
    plain = _normalized(text.strip())
    return any(pattern.search(plain) for pattern in _CLAIMS) or any(
        claim.search(plain) for claim, _ in _KINDS
    )


def effect_supported(
    messages: list[ModelMessage], effect_tools: Collection[str], text: str = ""
) -> bool:
    """Whether successful effect results of every claimed kind exist in this owner request."""
    plain = _normalized(text)
    required = [tool for claim, tool in _KINDS if claim.search(plain)] or [re.compile("")]
    return all(_supported(messages, effect_tools, tool) for tool in required)


def _supported(
    messages: list[ModelMessage], effect_tools: Collection[str], tool: re.Pattern[str]
) -> bool:
    names = {
        c.id: c.name
        for m in messages
        for c in m.tool_calls
        if c.name in effect_tools and tool.search(c.name)
    }
    for message in reversed(messages):
        if is_owner_message(message):
            return False
        if message.role != "tool" or message.tool_call_id not in names:
            continue
        try:
            raw: Any = json.loads(message.content)
        except ValueError:
            continue
        if not isinstance(raw, dict):
            continue
        data = cast(dict[str, Any], raw)
        if data.get("ok") is not False and data.get("status") not in {
            "failed",
            "rejected",
            "ambiguous",
        }:
            return True
    return False


@dataclass(frozen=True)
class ClaimVerdict:
    nudge: str | None = None
    replacement: str | None = None

    @property
    def passed(self) -> bool:
        return self.nudge is None and self.replacement is None


CLAIM_NUDGE = (
    "Your reply says an action was carried out, but no tool in this request completed it, "
    "so it did not happen. This check is Lonora's, not the owner's, and the owner has not "
    "read your draft: write the reply afresh, with no apology and no mention of this check. "
    "Either do it now with the right tool, or tell the owner plainly what has not been "
    "done and ask if something is missing. Owner "
    "controls are tools reached with tool_call when not native: a pause or no new trades "
    "is trade_restriction_create; resuming trading, lifting a pause, limits and authority "
    "are owner_action_propose cards that only the owner's tap applies (a card waits only "
    "once proposed); a watch is cancelled with watch_cancel or changed with watch_update; a "
    "recurring review is routine_create; an agent's model is model_list then model_request."
)


def claim_gate(
    state: dict[str, Any],
    messages: list[ModelMessage],
    text: str,
    effect_tools: Collection[str],
) -> ClaimVerdict:
    """One repair turn for an unsupported effect claim, then an honest line instead.

    The counter lives in the checkpoint and resets only on real owner input
    (``reset_stop_gate``), so restarts cannot buy more attempts.
    """
    if not claims_effect(text) or effect_supported(messages, effect_tools, text):
        return ClaimVerdict()
    attempts = state.get(_STATE_KEY, 0)
    if type(attempts) is not int or attempts < 1:
        state[_STATE_KEY] = 1
        return ClaimVerdict(nudge=CLAIM_NUDGE)
    # Another effect may have succeeded, so the line says only that the claim is unconfirmed.
    return ClaimVerdict(
        replacement="ما ذكرتُ أنه تم لم يؤكده أي إجراء في هذا الرد، فهو لم يحدث بعد. أخبرني "
        "إن أردت أن أحاول مرة أخرى."
        if prefers_arabic(messages)
        else "What I said was done is not confirmed by any action in this reply, so it has "
        "not happened yet. Tell me if you want me to try again."
    )


# Adopting or setting a limit, not remembering one (G0 I10: «اعتمد 1% كحد أقصى لكل صفقة»).
_LIMIT_SET = re.compile(
    r"(?:اعتمد|ثبت|ضع|حط|خلي|اجعل|حدد|عين|فعل)\S*\s.*(?:حد\s*(?:ال)?اقصي|الحد\s|حدود|مخاطره)|"
    r"\b(?:set|make|adopt|apply|use|put)\b.*\b(?:max(?:imum)?|limit|cap)\b|"
    r"\b(?:max(?:imum)?|limit|cap)\b.*\bto\s+\d"
)


_CODE_REQUEST = re.compile(
    r"كود|سكربت|سكريبت|برمج|اكسبرت|اكسبيرت|"
    r"\b(?:code|script|mql[45]|pine|python|javascript|expert advisor|ea)\b"
)
_FENCE = re.compile(r"```[^\n]*\n(.*?)(?:```|\Z)", re.DOTALL)


def code_requested(text: str) -> bool:
    return bool(_CODE_REQUEST.search(_normalized(text)))


def code_deliverable(messages: list[ModelMessage], text: str) -> bool:
    """D5: a substantial fenced block answering the owner's request for code."""
    if not code_requested(owner_words(messages)):
        return False
    return any(
        sum(1 for line in block.splitlines() if line.strip()) >= DELIVERABLE_LINES
        for block in _FENCE.findall(text)
    )


def code_decline(messages: list[ModelMessage]) -> str:
    return (
        "لا أسلّم الكود كمنتج، ومنه كود التداول مثل MQL5 وPine Script. أستطيع أن أشرح لك "
        "منطق المؤشر أو الاستراتيجية، أو أطبّقها تحليلًا على السوق وأنبّهك بالنتيجة."
        if prefers_arabic(messages)
        else "I don't hand over code as a deliverable, trading code included (MQL5, Pine "
        "Script). I can explain the indicator's or strategy's logic, or apply it to the "
        "market as analysis and alert you."
    )
