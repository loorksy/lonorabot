"""Deterministic reply guards keyed on the owner's own words and this request's results.

The owner's words are ``state["owner_request"]``: every message the owner typed that
started this Run (queued messages included) and the steering the owner typed while it
worked. Peer text, wake, watch and routine prompts and model text never enter it.

- ``request_refusal``: an explicit request to stop, pause or resume trading is never
  answered with a new entry, a limit to adopt never with a memory note, and the claim
  repair turn never increases risk. Exits, cancellations and protective changes run.
- ``claim_gate``: when the owner asked for an action and the reply says it is done, the
  structured results of this request decide: an uncertain effect appends a
  being-checked line, a confirmed effect passes, no effect gets one repair turn and then
  one appended line. Text and cards are never replaced.
- ``strip_code_deliverable``: D5, Lonora hands the owner no program as a product; only
  the program block is replaced.

The patterns are high-precision guards on a narrow set of phrasings, never routers: a
miss leaves the owner's own controls (the Stop trading switch, approval cards) intact.
"""

import json
import re
from collections.abc import Callable, Collection
from dataclasses import dataclass
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage, ToolCall

from .runtime_notices import is_owner_message

_STATE_KEY = "effect_claim_gate"
_REQUEST_KEY = "owner_request"
_START_KEY = "owner_request_start"
# Runs the owner started by typing; every other trigger is a wake that reports events.
OWNER_TRIGGERS = frozenset({"user", "group"})
# Entries and pending-entry edits: the class a no_new_entries restriction refuses.
ENTRY_ACTIONS = frozenset(
    {"buy", "sell", "buy_limit", "sell_limit", "buy_stop", "sell_stop", "modify_order"}
)
# A fenced block of at least this many lines answering a request for a program is a
# deliverable; a shorter one explains (Q36).
DELIVERABLE_LINES = 8
# RichContent holds at most this many parts.
MAXIMUM_PARTS = 24


def _normalized(text: str) -> str:
    """Arabic without diacritics or tatweel, one alef, yaa, haa and hamza form; lower Latin."""
    text = re.sub(r"[ً-ٰٟـ]", "", text)
    text = re.sub(r"[أإآٱ]", "ا", text).replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[ؤئ]", "ء", text)
    return text.lower()


# --- The owner's own request -------------------------------------------------------


def record_owner_request(state: dict[str, Any], trigger: str, messages: list[ModelMessage]) -> None:
    """On a Run's first entry: the owner-typed messages that started it.

    Queued owner messages arrive together after the last reply; every one of them is
    the request, not only the last.
    """
    if _REQUEST_KEY in state:
        return
    last = next(
        (i for i in range(len(messages) - 1, -1, -1) if is_owner_message(messages[i])), None
    )
    batch: list[int] = []
    for index in range(last if last is not None else -1, -1, -1):
        message = messages[index]
        if is_owner_message(message):
            batch.append(index)
        elif message.role != "system" and message.context_origin == "conversation":
            break
    if trigger in OWNER_TRIGGERS and batch:
        state[_REQUEST_KEY] = [messages[index].content for index in reversed(batch)]
        state[_START_KEY] = min(batch)
    else:
        state[_REQUEST_KEY] = []
        state[_START_KEY] = len(messages)


def add_owner_steering(state: dict[str, Any], text: str) -> None:
    """Owner-typed steering joins the request; it never replaces the first message."""
    if text.strip():
        state.setdefault(_REQUEST_KEY, []).append(text)


def owner_messages(state: dict[str, Any]) -> list[str]:
    words = state.get(_REQUEST_KEY)
    if not isinstance(words, list):
        return []
    return [item for item in cast(list[Any], words) if isinstance(item, str)]


def owner_words(state: dict[str, Any]) -> str:
    return "\n".join(owner_messages(state))


def _request_messages(state: dict[str, Any], messages: list[ModelMessage]) -> list[ModelMessage]:
    """Everything this Run added after the owner's messages, steering and peers included."""
    start = state.get(_START_KEY)
    return messages[start:] if type(start) is int and 0 <= start <= len(messages) else []


# --- Stop, pause and resume ----------------------------------------------------------

# A word start: the text start, a space or punctuation, then an optional wa/fa.
_W = r"(?:^|(?<=[\s،,.؛;:!؟?«\"(\-]))(?:و|ف)?"
_END = r"(?=\s|$|[.!،,:؛;؟?»\")])"
_STOP = [
    re.compile(
        _W
        + r"(?:اوقف|اوقفوا|وقف|وقفوا|علق|علقوا|جمد|جمدوا)"
        + r"\s+(?:(?:كل|جميع)\s+)?(?:ال)?(?:تداول|فتح\s+(?:ال)?صفقات|صفقات\s+(?:ال)?جديده|دخول)"
        + _END
    ),
    re.compile(_W + r"(?:توقف|توقفوا)\s+عن\s+(?:ال)?(?:تداول|فتح\s+(?:ال)?صفقات|دخول)" + _END),
    re.compile(
        r"\b(?:stop|pause|halt|suspend|freeze)\s+(?:all\s+|new\s+|my\s+)?trading\b|"
        r"\b(?:stop|pause)\s+(?:(?:taking|opening|entering|placing)\s+(?:any\s+|new\s+)*|"
        r"(?:all\s+|any\s+)?new\s+)(?:trades|positions|entries)\b"
    ),
]
_RESUME = [
    re.compile(
        _W
        + r"(?:استانف|استانفوا|استءناف|شغل|رجع)\s+(?:ال)?تداول"
        + _END
        + "|"
        + _W
        + r"(?:فك|ارفع|الغ)\s+(?:ال)?(?:ايقاف|توقف|تجميد)\s+(?:عن\s+)?(?:ال)?تداول"
        + _END
    ),
    re.compile(
        r"\b(?:resume|unpause|restart|re-?enable)\s+(?:the\s+|my\s+)?trading\b|"
        r"\bturn\s+trading\s+(?:back\s+)?on\b|\blift\s+the\s+trading\s+(?:pause|stop)\b"
    ),
]
# Negation counts only as the verb's own particle, immediately before it. The relative
# «ما» of «زي ما / مثل ما / على ما / كما» is not one.
_NEGATION_BEFORE = re.compile(
    r"(?:(?:^|\s)(?<!زي )(?<!مثل )(?<!علي )(?<!على )(?:لا|ما|مو|مش|لن|لم)\s+$)|"
    r"(?:\b(?:don'?t|do\s+not|never|won'?t)(?:\s+(?:want|need)\s+to)?\s+$)|"
    r"(?:\bno\s+need\s+to\s+$)"
)


def _fires(patterns: list[re.Pattern[str]], text: str) -> bool:
    plain = _normalized(text)
    return any(
        not _NEGATION_BEFORE.search(plain[: match.start()].rstrip() + " ")
        for pattern in patterns
        for match in pattern.finditer(plain)
    )


def stop_requested(text: str) -> bool:
    return _fires(_STOP, text)


def resume_requested(text: str) -> bool:
    return _fires(_RESUME, text)


def _any_message(state: dict[str, Any], check: Callable[[str], bool]) -> bool:
    return any(check(text) for text in owner_messages(state))


_CANCEL_REQUEST = re.compile(
    _W + r"(?:الغ|الغي|احذف|امسح)" + _END + r"|\b(?:cancel|delete|remove)\b"
)
_MODEL_REQUEST = re.compile(
    r"نموذج\s+(?:ال)?ذكاء|موديل|\b(?:ai|language)\s+model\b|\bllm\b|\bmodel\s+(?:for|of)\b"
)


def requested_tools(state: dict[str, Any]) -> list[str]:
    """Owner-control tools the owner's words call for, offered natively for this Run.

    Presentation only: they join the promoted set within its budget and the Run's
    scope, and execution still validates every call.
    """
    plain = _normalized(owner_words(state))
    names: list[str] = []
    if _any_message(state, stop_requested):
        names.append("trade_restriction_create")
    if _CANCEL_REQUEST.search(plain):
        names += ["watch_list", "watch_cancel"]
    if _MODEL_REQUEST.search(plain):
        names += ["model_list", "model_request"]
    return names


# --- Calls refused before they run ---------------------------------------------------


@dataclass(frozen=True)
class GoalTradeIntent:
    """The trade a goal step would place: its action and whether it clears the stop."""

    action: str
    clear_stop_loss: bool = False


def _risk_increasing(call: ToolCall, goal: GoalTradeIntent | None) -> bool:
    """A new or larger exposure, or a removed stop. Exits, cancels and tightening are not."""
    if call.name == "goal_step_execute":
        return goal is not None and (
            goal.action in ENTRY_ACTIONS
            or (goal.action == "modify_position" and goal.clear_stop_loss)
        )
    if call.name != "trade_execute":
        return False
    action = call.arguments.get("action")
    return action in ENTRY_ACTIONS or (
        action == "modify_position" and bool(call.arguments.get("clear_stop_loss"))
    )


# Adopting or setting a limit, not remembering one (G0 I10: «اعتمد 1% كحد أقصى لكل صفقة»).
_LIMIT_SET = re.compile(
    _W + r"(?:اعتمد|ثبت|ضع|حط|خلي|اجعل|حدد|عين)\s.*(?:حد\s*(?:ال)?اقصي|الحد\s|حدود|مخاطره)|"
    r"\b(?:set|make|adopt|apply|use|put)\b.*\b(?:max(?:imum)?|limit|cap)\b|"
    r"\b(?:max(?:imum)?|limit|cap)\b.*\bto\s+\d"
)


def limit_requested(text: str) -> bool:
    return bool(_LIMIT_SET.search(_normalized(text)))


def request_refusal(
    state: dict[str, Any], call: ToolCall, *, goal: GoalTradeIntent | None = None
) -> dict[str, Any] | None:
    """The refused result of a call that cannot answer the owner's request.

    ``goal`` is the trade the goal step of a ``goal_step_execute`` would place (``None``
    for a step that trades nothing).
    """
    increasing = _risk_increasing(call, goal)
    if increasing and state.get(_STATE_KEY) == 1:
        return {
            "ok": False,
            "code": "claim_repair_no_new_risk",
            "executed": False,
            "message": "This turn only corrects a reply that claimed an action; it cannot "
            "open or increase exposure, and nothing was sent. Closing, cancelling and "
            "protecting stay possible. Tell the owner plainly what is not confirmed.",
        }
    if call.name == "memory_write" and _any_message(state, limit_requested):
        return {
            "ok": False,
            "code": "owner_limit_request_not_memory",
            "executed": False,
            "message": "The owner asked to adopt a limit; memory enforces nothing and was not "
            "changed. Propose it with owner_action_propose kind set_account_limits (through "
            "tool_call) now; once it is proposed, the card waits for the owner's tap.",
        }
    if not increasing:
        return None
    if _any_message(state, stop_requested):
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
    if _any_message(state, resume_requested):
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


# --- Effect claims -------------------------------------------------------------------

_ACTION_REQUEST = [
    re.compile(
        _W + r"(?:الغ|الغي|احذف|امسح|شيل|عدل|غير|خلي|خليه|خليها|حط|ضع|اضبط|فعل|شغل|اوقف|وقف|"
        r"علق|استانف|ارفع|فك|اعتمد|حدد|جدول|ذكرني|نبهني|انشء|سوي|اعمل|اجعل|ثبت|انقل|"
        r"اشتر|اشتري|بيع|سكر|اغلق|افتح)(?:ه|ها|هم|لي|ني)?" + _END
    ),
    re.compile(
        r"\b(?:cancel|delete|remove|set|change|move|make|create|pause|stop|resume|lift|"
        r"schedule|remind|alert|notify|buy|sell|close|open|adopt|apply|update|switch|"
        r"add|turn)\b"
    ),
]


def action_requested(words: str) -> bool:
    plain = _normalized(words)
    return any(pattern.search(plain) for pattern in _ACTION_REQUEST)


# Lonora objects a completion claim can be about, stop loss and take profit included.
_AR_OBJECT = (
    r"(?:ال)?(?:تنبيه|تنبيهات|مراقبه|شرط|تداول|صفقه|صفقات|امر|اوامر|حد|حدود|مخاطره|مهمه|"
    r"موعد|تذكير|روتين|قيد|حظر|ايقاف|بطاقه|طلب|مستوي|هدف|وقف\s+(?:ال)?خساره|"
    r"جني\s+(?:ال)?ربح)(?:ا|ها)?"
)
_EN_OBJECT = (
    r"(?:alert|alerts|watch|trading|trade|trades|position|positions|order|orders|limit|limits|"
    r"restriction|pause|routine|reminder|schedule|card|request|stop[\s-]loss|take[\s-]profit|"
    r"sl|tp|target)"
)
_AR_VERBS = (
    r"الغيت|لغيت|حذفت|ازلت|شلت|اوقفت|وقفت|جمدت|علقت|استانفت|اغلقت|سكرت|عدلت|غيرت|انشات|"
    r"انشءت|فعلت|شغلت|ضبطت|اضفت|ارسلت|جدولت|اعتمدت|نقلت|رفعت|خفضت|وضعت|حطيت"
)
_AR_NOUNS = (
    r"الغاء|حذف|ايقاف|تجميد|تعليق|استءناف|اغلاق|تعديل|ضبط|تفعيل|انشاء|جدوله|اعتماد|"
    r"تغيير|تثبيت|رفع|نقل|وضع|حفظ"
)
_EN_VERBS = (
    r"cancel+ed|removed|deleted|paused|stopped|halted|resumed|closed|set|created|updated|"
    r"changed|scheduled|enabled|added|adjusted|moved|switched|applied|placed|raised|lowered|"
    r"tightened"
)
_SENTENCE = r"(?:^|(?<=[\n.!؟?:;]))\s*"
_CLAIMS = [
    # «تم.» / «تم الإلغاء.» / "Done." standing alone answers the owner's own request.
    re.compile(_SENTENCE + r"(?:تم+|done|all\s+set)\s*(?:[.!،,✅]|$)"),
    re.compile(_SENTENCE + r"تم+\s+(?:ال)?(?:" + _AR_NOUNS + r")(?:ه|ها)?\s*(?:[.!،,✅]|$)"),
    # «ألغيت التنبيه», «عدّلت وقف الخسارة», «تم إلغاء التنبيه», «تم إلغاؤه».
    re.compile(
        _W
        + r"(?:لقد\s+|قد\s+)?(?:"
        + _AR_VERBS
        + r")(?:ه|ها)?"
        + _END
        + r"(?:\s+\S+){0,2}?\s+"
        + _AR_OBJECT
        + _END
    ),
    re.compile(_W + r"تم+\s+(?:ال)?(?:" + _AR_NOUNS + r")(?:ه|ها)" + _END),
    re.compile(
        _W
        + r"تم+\s+(?:ال)?(?:"
        + _AR_NOUNS
        + r")"
        + _END
        + r"(?:\s+\S+){0,2}?\s+"
        + _AR_OBJECT
        + _END
    ),
    re.compile(
        r"\bi(?:'ve|\s+have)?\s+(?:now\s+|just\s+|already\s+)?(?:" + _EN_VERBS + r")\b"
        r"(?:\s+\S+){0,3}?\s+"
        + _EN_OBJECT
        + r"\b|"
        + _SENTENCE
        + r"(?:"
        + _EN_VERBS
        + r")\s+(?:the|your|all)\s+"
        + _EN_OBJECT
        + r"\b"
    ),
    # A card the owner taps.
    re.compile(
        r"(?:بانتظار|تنتظر|ينتظر)\s+(?:\S+\s+)?(?:لمس|نقر|موافق|توقيع|تاكيد)|"
        r"\bwait(?:s|ing)\b.{0,30}\b(?:tap|approval|confirmation|signature)\b"
    ),
]
# A denial of the claimed action, immediately or one word before it.
_DENIAL_BEFORE = re.compile(
    r"(?:(?:^|\s)(?:لا|ما|لم|لن|ليس)\s+(?:\S+\s+)?$)|"
    r"(?:\b(?:not|never|haven'?t|hasn'?t|didn'?t|won'?t)\s+(?:\S+\s+)?$)"
)


def _claim_text(text: str) -> str:
    """The reply's prose: no fenced blocks and no table rows."""
    kept = [line for line in _prose_lines(text) if not line.lstrip().startswith("|")]
    return "\n".join(kept)


def claims_effect(text: str) -> bool:
    """A first-person completion claim (high precision; denials are not claims)."""
    plain = _normalized(_claim_text(text).strip())
    return any(
        not _DENIAL_BEFORE.search(plain[: match.start()] + " ")
        for pattern in _CLAIMS
        for match in pattern.finditer(plain)
    )


# Tools whose successful result is an effect a claim may report. Memory and notes are not.
_EFFECT_TOOLS = re.compile(
    r"^(?:trade_|goal_|watch_|routine_|task_|owner_action_)|"
    r"^(?:model_request|agent_create|supervision_create|chart_create)$"
)
_UNCERTAIN_CODES = {"tool_execution_uncertain", "broker_result_ambiguous", "operation_ambiguous"}
_UNCERTAIN_STATUSES = {"ambiguous", "operation_ambiguous", "submitted", "reserved", "uncertain"}


def _outcome(raw: str) -> str:
    """``confirmed``, ``uncertain`` or ``failed`` for one tool result."""
    try:
        data: Any = json.loads(raw)
    except ValueError:
        return "failed"
    if not isinstance(data, dict):
        return "failed"
    result = cast(dict[str, Any], data)
    rows: Any = result.get("results", [result])
    listed = cast(list[Any], rows) if isinstance(rows, list) else [result]
    statuses = {cast(dict[str, Any], row).get("status") for row in listed if isinstance(row, dict)}
    if result.get("code") in _UNCERTAIN_CODES or statuses & _UNCERTAIN_STATUSES:
        return "uncertain"
    if result.get("ok") is False or statuses & {"failed", "rejected"}:
        return "failed"
    return "confirmed"


def _effects(
    state: dict[str, Any], messages: list[ModelMessage], effect_tools: Collection[str]
) -> set[str]:
    """The outcomes of every effect call in this request, earlier rounds included."""
    request = _request_messages(state, messages)
    calls = {
        c.id
        for m in request
        for c in m.tool_calls
        if c.name in effect_tools and _EFFECT_TOOLS.search(c.name)
    }
    return {_outcome(m.content) for m in request if m.role == "tool" and m.tool_call_id in calls}


@dataclass(frozen=True)
class ClaimVerdict:
    nudge: str | None = None
    # One honest line appended to the reply; the reply and its card are kept.
    appended: str | None = None

    @property
    def passed(self) -> bool:
        return self.nudge is None and self.appended is None


CLAIM_NUDGE = (
    "Your reply says an action was carried out, but no tool in this request carried one "
    "out. This check is Lonora's, not the owner's, and the owner has not read your draft: "
    "write the reply afresh, with no apology and no mention of this check. Either do it now "
    "with the right tool, or tell the owner plainly what is not done yet and ask if "
    "something is missing. Owner controls are tools reached with tool_call when not "
    "native: a pause or no new trades is trade_restriction_create; resuming trading, "
    "lifting a pause, limits and authority are owner_action_propose cards that only the "
    "owner's tap applies (a card waits only once proposed); a watch is cancelled with "
    "watch_cancel or changed with watch_update; a recurring review is routine_create; an "
    "agent's model is model_list then model_request."
)


def _arabic(words: str) -> bool:
    return bool(re.search(r"[ؠ-ي]", words)) or not re.search(r"[A-Za-z]{3}", words)


def _line(words: str, uncertain: bool) -> str:
    if uncertain:
        return (
            "نتيجة ذلك غير مؤكدة بعد، وأتحقق منها؛ لن أعيد الإرسال."
            if _arabic(words)
            else "The outcome is not confirmed yet and is being checked; I will not resend it."
        )
    return "لم أتمكن من تأكيد ذلك بعد." if _arabic(words) else "I could not confirm that yet."


def claim_gate(
    state: dict[str, Any],
    messages: list[ModelMessage],
    text: str,
    effect_tools: Collection[str],
) -> ClaimVerdict:
    """The verdict for a reply that says the owner's requested action is done.

    Over every effect call of this request: an uncertain one appends the being-checked
    line and is never repaired (a repair could resend it); a confirmed one passes; none
    gets one repair turn, then the honest line. The counter lives in the checkpoint and
    resets only on real owner input (``reset_stop_gate``).
    """
    words = owner_words(state)
    if not words or not action_requested(words) or not claims_effect(text):
        return ClaimVerdict()
    outcomes = _effects(state, messages, effect_tools)
    if "uncertain" in outcomes:
        return ClaimVerdict(appended=_line(words, True))
    if "confirmed" in outcomes:
        return ClaimVerdict()
    if state.get(_STATE_KEY) != 1:
        state[_STATE_KEY] = 1
        return ClaimVerdict(nudge=CLAIM_NUDGE)
    return ClaimVerdict(appended=_line(words, False))


def report_line(
    state: dict[str, Any], messages: list[ModelMessage], text: str, effect_tools: Collection[str]
) -> str | None:
    """The line for the tool-less final report at a limit.

    The limit stop is that report's own effect, so only a claim the repair turn already
    asked to correct, still unsupported, gets a line.
    """
    if state.get(_STATE_KEY) != 1:
        return None
    verdict = claim_gate(state, messages, text, effect_tools)
    return verdict.appended


def appended_parts(parts: list[Any], line: str) -> list[Any]:
    """The card's parts with the line: a new text part, or the last text part within the cap."""
    if len(parts) < MAXIMUM_PARTS:
        return [*parts, {"type": "text", "text": line}]
    for index in range(len(parts) - 1, -1, -1):
        part = parts[index]
        if isinstance(part, dict) and cast(dict[str, Any], part).get("type") == "text":
            updated = dict(cast(dict[str, Any], part))
            updated["text"] = str(updated.get("text", "")).rstrip() + "\n\n" + line
            return [*parts[:index], updated, *parts[index + 1 :]]
    return parts


# --- D5: no program as a deliverable ---------------------------------------------------

_LANGUAGE = re.compile(
    r"\b(?:mql4|mql5|pine\s*script|pinescript|pine|python|javascript|typescript|java|lua|"
    r"rust|golang|bash|powershell|vba|ninjascript|easylanguage|afl)\b|c\+\+|c#|"
    r"بايثون|جافا\s*سكربت|جافا|سي\s*شارب|سي\s*بلس"
)
_PROGRAM = re.compile(
    _W + r"(?:ال)?(?:اكسبرت|اكسبيرت|سكربت|سكريبت|روبوت|بوت|برنامج|مءشر|كود)(?!\s+(?:ال)?(?:خطا|"
    r"الخطا|دعوه|الدعوه|تفعيل|التفعيل|خصم|الخصم|تحقق|التحقق|خطء))"
    r"|\b(?:ea|expert\s+advisor|script|bot|program|indicator|code)\b(?!\s+(?:error|for\s+the\s+error))"
)
_STRATEGY = re.compile(_W + r"(?:ال)?استراتيجيه|\bstrategy\b")
_WRITE = re.compile(
    _W
    + r"(?:اكتب|ابن|ابني|برمج|اعمل|سوي|اعطني|عطني)"
    + _END
    + r"|\b(?:write|build|make|create|give\s+me|code\s+(?:me|a|an|up|this))\b"
)


def code_requested(words: str) -> bool:
    """An explicit request to write a program: an EA, indicator, script, bot or code.

    A named programming language makes a strategy a program too; «بلغة بسيطة» and
    error-code questions are not requests for one.
    """
    plain = _normalized(words)
    if not _WRITE.search(plain):
        return False
    if _PROGRAM.search(plain):
        return True
    return bool(_LANGUAGE.search(plain) and _STRATEGY.search(plain))


# Fences that carry display data or text, never a program.
_DISPLAY_FENCES = frozenset(
    {
        "lonora-ui",
        "json",
        "mermaid",
        "diagram",
        "config",
        "log",
        "table",
        "yaml",
        "toml",
        "ini",
        "csv",
        "text",
    }
)
_OPEN = re.compile(r"^(?P<indent> {0,3})(?P<mark>`{3,}|~{3,})(?P<info>[^\n]*)$")


def _blocks(lines: list[str]) -> list[tuple[int, int, str]]:
    """``(open, close, info)`` line indexes of each fenced block (CommonMark rules).

    A closing fence uses the same character at least as long as the opening one, so a
    four-backtick fence holds ``` lines; an unclosed fence runs to the end.
    """
    found: list[tuple[int, int, str]] = []
    index = 0
    while index < len(lines):
        opened = _OPEN.match(lines[index])
        if opened is None or (opened["mark"][0] == "`" and "`" in opened["info"]):
            index += 1
            continue
        mark = opened["mark"]
        close = re.compile(r"^ {0,3}" + re.escape(mark[0]) + "{" + str(len(mark)) + r",}\s*$")
        end = next((j for j in range(index + 1, len(lines)) if close.match(lines[j])), len(lines))
        found.append((index, end, opened["info"].strip().lower()))
        index = end + 1
    return found


def _prose_lines(text: str) -> list[str]:
    lines = text.splitlines()
    inside: set[int] = set()
    for opened, closed, _ in _blocks(lines):
        inside.update(range(opened, min(closed, len(lines) - 1) + 1))
    return [line for index, line in enumerate(lines) if index not in inside]


def code_decline(words: str) -> str:
    return (
        "لا أسلّم الكود كمنتج، ومنه كود التداول مثل MQL5 وPine Script. أستطيع أن أشرح لك "
        "منطق المؤشر أو الاستراتيجية، أو أطبّقها تحليلًا على السوق وأنبّهك بالنتيجة."
        if _arabic(words)
        else "I don't hand over code as a deliverable, trading code included (MQL5, Pine "
        "Script). I can explain the indicator's or strategy's logic, or apply it to the "
        "market as analysis and alert you."
    )


def strip_code_deliverable(words: str, text: str) -> str:
    """Replace each program block answering a request for one with a single decline.

    Display fences (``lonora-ui`` with or without more info, json, mermaid, diagram,
    config, log, table) and blocks under DELIVERABLE_LINES (Q36) stay, and so does the
    rest of the reply.
    """
    if not code_requested(words):
        return text
    lines = text.splitlines()
    out: list[str] = []
    position = 0
    declined = False
    for opened, closed, info in _blocks(lines):
        language = info.split()[0] if info.split() else ""
        body = lines[opened + 1 : closed]
        if (
            language in _DISPLAY_FENCES
            or language.startswith("lonora-ui")
            or sum(1 for line in body if line.strip()) < DELIVERABLE_LINES
        ):
            continue
        out.extend(lines[position:opened])
        if not declined:
            out.append(code_decline(words))
            declined = True
        position = closed + 1
    out.extend(lines[position:])
    return "\n".join(out) + ("\n" if text.endswith("\n") and out else "")
