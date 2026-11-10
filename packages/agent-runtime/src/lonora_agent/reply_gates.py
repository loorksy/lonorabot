"""Deterministic reply guards keyed on the owner's own words and this request's results.

The owner's words are ``state["owner_request"]``: the message the owner typed that
started this Run and the steering the owner typed while it worked. Peer text, wake,
watch and routine prompts and model text never enter it (``record_owner_request``,
``add_owner_steering``).

- ``request_refusal``: a request to stop, pause or resume trading is never answered
  with a new entry, a limit to adopt never with a memory note, and the claim repair
  turn never increases risk. Exits, cancellations and protective changes always run.
- ``claim_gate`` / ``unconfirmed_line``: when the owner asked for an action, a reply
  that says the reply's own action on a Lonora object happened needs a successful result
  of the matching kind in this request. One repair turn, then one honest line is
  appended; the reply and its card are kept.
- ``strip_code_deliverable``: D5, Lonora hands the owner no program as a product. Only
  the code block is replaced; Q36 explanation blocks and display fences stay.

The patterns are guards on a narrow set of phrasings, never request routers.
"""

import json
import re
from collections.abc import Collection, Sequence
from dataclasses import dataclass
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage, ToolCall

from .runtime_notices import is_owner_message

_STATE_KEY = "effect_claim_gate"
_REQUEST_KEY = "owner_request"
_START_KEY = "owner_request_start"
# Runs the owner started by typing; every other trigger is a wake with server or
# model text, which reports events instead of answering an owner request.
OWNER_TRIGGERS = frozenset({"user", "group"})
# Entries and pending-entry edits: the class a no_new_entries restriction refuses.
ENTRY_ACTIONS = frozenset(
    {"buy", "sell", "buy_limit", "sell_limit", "buy_stop", "sell_stop", "modify_order"}
)
# A fenced block of at least this many lines answering a request for a program is a
# deliverable; a shorter one explains (Q36).
DELIVERABLE_LINES = 8
# Fences that carry display data, never a program.
_DISPLAY_FENCES = frozenset({"lonora-ui", "json", "mermaid", "diagram"})


def _normalized(text: str) -> str:
    """Arabic without diacritics or tatweel, one alef, yaa, haa and hamza form; lower Latin."""
    text = re.sub(r"[ً-ٰٟـ]", "", text)
    text = re.sub(r"[أإآٱ]", "ا", text).replace("ى", "ي").replace("ة", "ه")
    text = re.sub(r"[ؤئ]", "ء", text)
    return text.lower()


# --- The owner's own request -------------------------------------------------------


def record_owner_request(state: dict[str, Any], trigger: str, messages: list[ModelMessage]) -> None:
    """On a Run's first entry: the owner-typed message that started it, if any."""
    if _REQUEST_KEY in state:
        return
    index = next(
        (i for i in range(len(messages) - 1, -1, -1) if is_owner_message(messages[i])), None
    )
    if trigger in OWNER_TRIGGERS and index is not None:
        state[_REQUEST_KEY] = [messages[index].content]
        state[_START_KEY] = index
    else:
        state[_REQUEST_KEY] = []
        state[_START_KEY] = len(messages)


def add_owner_steering(state: dict[str, Any], text: str) -> None:
    """Owner-typed steering joins the request; it never replaces the first message."""
    if text.strip():
        state.setdefault(_REQUEST_KEY, []).append(text)


def owner_words(state: dict[str, Any]) -> str:
    words = state.get(_REQUEST_KEY)
    if not isinstance(words, list):
        return ""
    return "\n".join(item for item in cast(list[Any], words) if isinstance(item, str))


def _request_messages(state: dict[str, Any], messages: list[ModelMessage]) -> list[ModelMessage]:
    """Everything this Run added after the owner's message, steering and peers included."""
    start = state.get(_START_KEY)
    return messages[start:] if type(start) is int and 0 <= start <= len(messages) else []


# --- Recognisers over the owner's words ----------------------------------------------

# A word start: the text start, a space or punctuation, then an optional wa/fa.
_W = r"(?:^|(?<=[\s،,.؛;:!؟?«\"(\-]))(?:و|ف)?"
_NEGATION = re.compile(
    r"(?:^|\s)(?:لا|ما|مو|مش|لن|لم|ليس|بلاش)(?:\s|$)|"
    r"\b(?:don'?t|do\s+not|doesn'?t|not|never|no\s+need|haven'?t|hasn'?t|didn'?t|won'?t)\b"
)


def _negated(plain: str, start: int) -> bool:
    """A negation among the three words before a match, within its clause."""
    clause = re.split(r"[.،,؛;!؟?\n]", plain[:start])[-1]
    return bool(_NEGATION.search(" " + " ".join(clause.split()[-3:]) + " "))


def _affirmed(patterns: Sequence[re.Pattern[str]], text: str) -> bool:
    plain = _normalized(text)
    return any(
        not _negated(plain, match.start())
        for pattern in patterns
        for match in pattern.finditer(plain)
    )


_FILLERS = r"(?:\s+(?:كل|جميع|عن|لي|مءقتا|حاليا|فورا|الان))*"
_STOP = [
    # A stop-trading phrase: the verb at a word start and a trading object. A stop
    # loss (الوقف، وقف الخسارة، SL) has no trading object after the verb.
    re.compile(
        _W
        + r"(?:اوقف|اوقفوا|وقف|وقفوا|توقف|ايقاف|جمد|جمدوا|تجميد)"
        + _FILLERS
        + r"\s+(?:ال)?(?:تداول|دخول|صفقات\s+(?:ال)?جديده)"
    ),
    re.compile(_W + r"(?:ممنوع|بدون|بلا)\s+(?:ال)?(?:تداول|صفقات\s+(?:ال)?جديده|دخول)"),
    re.compile(
        r"\b(?:stop|pause|halt|suspend|freeze)\b(?:\s+(?:all|the|my|any|new|opening|placing))*"
        r"\s+(?:trading|trades|entries|positions|buying|selling)\b"
    ),
    re.compile(r"\bno\s+(?:new|more)\s+(?:trades?|positions|entries)\b"),
]
# A prohibition is a stop by itself; it is not read through the negation window.
_PROHIBIT = [
    re.compile(_W + r"لا\s+(?:ت|ن)(?:فتح|تداول|دخل)(?=\s|$|[.!،,])"),
    re.compile(
        r"\b(?:don'?t|do\s+not)\s+(?:trade\b|(?:open|enter|place)\s+(?:any\s+|new\s+)*"
        r"(?:trades?|positions|entries|orders)\b)"
    ),
]
_RESUME = [
    re.compile(_W + r"(?:استانف|استانفوا|استءناف)(?=\s|$|[.!،,؟?])"),
    re.compile(_W + r"(?:ارفع|فك|الغ|الغي|شيل)\s+(?:ال)?(?:ايقاف|توقف|تجميد)(?=\s|$|[.!،,؟?])"),
    re.compile(_W + r"(?:شغل|فعل|رجع)\s+(?:ال)?تداول"),
    re.compile(
        r"\b(?:resume|unpause|restart|re-?enable)\s+(?:the\s+|my\s+)?trading\b|"
        r"\bturn\s+trading\s+(?:back\s+)?on\b|\blift\s+the\s+(?:pause|stop|freeze)\b|"
        r"\bresume\b(?=\s*$|\s*[.!])"
    ),
]


def stop_requested(text: str) -> bool:
    plain = _normalized(text)
    return _affirmed(_STOP, text) or any(pattern.search(plain) for pattern in _PROHIBIT)


def resume_requested(text: str) -> bool:
    return _affirmed(_RESUME, text)


_CANCEL_REQUEST = [
    re.compile(_W + r"(?:الغ|الغي|الغاء|احذف|امسح)(?=\s|$)|\b(?:cancel|delete|remove)\b")
]
_MODEL_REQUEST = [
    re.compile(
        r"نموذج\s+(?:ال)?ذكاء|موديل|\b(?:ai|language)\s+model\b|\bllm\b|\bmodel\s+(?:for|of)\b"
    )
]


def requested_tools(state: dict[str, Any]) -> list[str]:
    """Owner-control tools the owner's words call for, offered natively for this Run.

    Presentation only: they join the promoted set within its budget and the Run's
    scope, and execution still validates every call.
    """
    words = owner_words(state)
    names: list[str] = []
    if stop_requested(words):
        names.append("trade_restriction_create")
    if _affirmed(_CANCEL_REQUEST, words):
        names += ["watch_list", "watch_cancel"]
    if _affirmed(_MODEL_REQUEST, words):
        names += ["model_list", "model_request"]
    return names


_ACTION_REQUEST = [
    re.compile(
        _W + r"(?:الغ|الغي|احذف|امسح|شيل|عدل|غير|خلي|خليه|خليها|حط|ضع|اضبط|فعل|شغل|اوقف|وقف|"
        r"استانف|ارفع|فك|سجل|احفظ|اعتمد|حدد|جدول|ذكرني|نبهني|انشء|سوي|اعمل|اجعل|ثبت|انقل|"
        r"اشتر|اشتري|بيع|سكر|اغلق|افتح)(?:ه|ها|هم|لي|ني)?(?=\s|$|[.!،,؟?])"
    ),
    re.compile(
        r"\b(?:cancel|delete|remove|set|change|move|make|create|save|remember|record|pause|"
        r"stop|resume|lift|schedule|remind|alert|notify|buy|sell|close|open|adopt|apply|"
        r"update|switch|add|log|turn)\b"
    ),
]


def action_requested(words: str) -> bool:
    return _affirmed(_ACTION_REQUEST, words)


# Adopting or setting a limit, not remembering one (G0 I10: «اعتمد 1% كحد أقصى لكل صفقة»).
_LIMIT_SET = [
    re.compile(
        _W + r"(?:اعتمد|ثبت|ضع|حط|خلي|اجعل|حدد|عين)\s.*(?:حد\s*(?:ال)?اقصي|الحد\s|حدود|مخاطره)"
    ),
    re.compile(r"\b(?:set|make|adopt|apply|use|put)\b.*\b(?:max(?:imum)?|limit|cap)\b"),
    re.compile(r"\b(?:max(?:imum)?|limit|cap)\b.*\bto\s+\d"),
]


# --- Calls refused before they run ---------------------------------------------------


def _risk_increasing(call: ToolCall, goal_action: str | None) -> bool:
    """A new or larger exposure, or a removed stop. Exits, cancels and tightening are not."""
    if call.name == "goal_step_execute":
        return goal_action in ENTRY_ACTIONS
    if call.name != "trade_execute":
        return False
    action = call.arguments.get("action")
    return action in ENTRY_ACTIONS or (
        action == "modify_position" and bool(call.arguments.get("clear_stop_loss"))
    )


def request_refusal(
    state: dict[str, Any], call: ToolCall, *, goal_action: str | None = None
) -> dict[str, Any] | None:
    """The refused result of a call that cannot answer the owner's request.

    ``goal_action`` is the trade action of the goal step a ``goal_step_execute`` would
    run (``None`` for a step that trades nothing).
    """
    increasing = _risk_increasing(call, goal_action)
    if increasing and state.get(_STATE_KEY) == 1:
        return {
            "ok": False,
            "code": "claim_repair_no_new_risk",
            "executed": False,
            "message": "This turn only corrects a reply that claimed an action; it cannot "
            "open or increase exposure, and nothing was sent. Closing, cancelling and "
            "protecting stay possible. Tell the owner plainly what is not confirmed.",
        }
    words = owner_words(state)
    if call.name == "memory_write" and _affirmed(_LIMIT_SET, words):
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


# --- Effect claims -------------------------------------------------------------------

# Lonora objects an action claim can be about.
_AR_OBJECT = (
    r"(?:ال)?(?:تنبيه|تنبيهات|مراقبه|شرط|تداول|صفقه|صفقات|امر|اوامر|حد|حدود|مخاطره|مهمه|"
    r"موعد|تذكير|روتين|ذاكره|ملاحظه|قيد|حظر|ايقاف|بطاقه|طلب|مستوي)(?:ا|ها)?"
)
_EN_OBJECT = (
    r"(?:alert|alerts|watch|trading|trade|trades|position|positions|order|orders|limit|limits|"
    r"restriction|pause|routine|reminder|schedule|memory|note|card|request)"
)
# The kinds a claim can be, each read from its verb.
_AR_VERBS = {
    "cancel": r"الغيت|لغيت|حذفت|ازلت|شلت",
    "stop": r"اوقفت|وقفت|جمدت",
    "resume": r"استانفت",
    "close": r"اغلقت|سكرت",
    "generic": r"حفظت|عدلت|غيرت|انشات|انشءت|فعلت|شغلت|ضبطت|اضفت|ارسلت|جدولت|اعتمدت|"
    r"نقلت|رفعت|خفضت|سجلت",
}
_AR_NOUNS = {
    "cancel": r"الغاء|حذف",
    "stop": r"ايقاف|تجميد",
    "resume": r"استءناف",
    "close": r"اغلاق",
    "generic": r"حفظ|تعديل|ضبط|تفعيل|انشاء|جدوله|اعتماد|تسجيل|تغيير|تثبيت|رفع|نقل",
}
_EN_VERBS = {
    "cancel": r"cancel+ed|removed|deleted",
    "stop": r"paused|stopped|halted|frozen",
    "resume": r"resumed|unpaused",
    "close": r"closed",
    "generic": r"saved|set|created|updated|changed|scheduled|enabled|added|adjusted|moved|"
    r"switched|recorded|logged|applied|placed|raised|lowered",
}
_SENTENCE = r"(?:^|(?<=[\n.!؟?:;]))\s*"
_END = r"(?=\s|$|[.!،,:])"


def _claim_patterns() -> list[tuple[str, re.Pattern[str]]]:
    found: list[tuple[str, re.Pattern[str]]] = [
        # «تم.» / "Done." standing alone answers the owner's own request.
        ("generic", re.compile(_SENTENCE + r"(?:تم+|done|all\s+set)\s*(?:[.!،,✅]|$)")),
        (
            "card",
            re.compile(
                r"(?:بانتظار|تنتظر|ينتظر)\s+(?:\S+\s+)?(?:لمس|نقر|موافق|توقيع|تاكيد)|"
                r"\bwait(?:s|ing)\b.{0,30}\b(?:tap|approval|confirmation|signature)\b"
            ),
        ),
    ]
    for kind, verbs in _AR_VERBS.items():
        # First person past with the object it acts on: «ألغيت التنبيه».
        found.append(
            (
                kind,
                re.compile(
                    _W
                    + r"(?:لقد\s+|قد\s+)?(?:"
                    + verbs
                    + r")(?:ه|ها)?"
                    + _END
                    + r"(?:\s+\S+){0,2}?\s+"
                    + _AR_OBJECT
                    + _END
                ),
            )
        )
    for kind, nouns in _AR_NOUNS.items():
        # «تم إلغاء التنبيه», or «تم إلغاؤه» with the object as a pronoun.
        found.append(
            (
                kind,
                re.compile(
                    _W
                    + r"تم+\s+(?:ال)?(?:"
                    + nouns
                    + r")(?:ه|ها)"
                    + _END
                    + "|"
                    + _W
                    + r"تم+\s+(?:ال)?(?:"
                    + nouns
                    + r")"
                    + _END
                    + r"(?:\s+\S+){0,2}?\s+"
                    + _AR_OBJECT
                    + _END
                ),
            )
        )
    for kind, verbs in _EN_VERBS.items():
        found.append(
            (
                kind,
                re.compile(
                    r"\bi(?:'ve|\s+have)?\s+(?:now\s+|just\s+|already\s+)?(?:" + verbs + r")\b"
                    r"(?:\s+\S+){0,3}?\s+"
                    + _EN_OBJECT
                    + r"\b|"
                    + _SENTENCE
                    + r"(?:"
                    + verbs
                    + r")\s+(?:the|your|all)\s+"
                    + _EN_OBJECT
                    + r"\b"
                ),
            )
        )
    return found


_CLAIMS = _claim_patterns()


def _claim_text(text: str) -> str:
    """The reply's prose: no fences, no table rows (an order table is not a claim)."""
    text = re.sub(r"(?ms)^(```|~~~).*?^\1[ \t]*$", " ", text)
    return "\n".join(line for line in text.splitlines() if not line.lstrip().startswith("|"))


def claim_kinds(text: str) -> set[str]:
    """The kinds of affirmative action claims the reply makes."""
    plain = _normalized(_claim_text(text).strip())
    return {
        kind
        for kind, pattern in _CLAIMS
        for match in pattern.finditer(plain)
        if not _negated(plain, match.start())
    }


def claims_effect(text: str) -> bool:
    return bool(claim_kinds(text))


_CARD_TOOLS = re.compile(
    r"owner_action_propose|model_request|agent_create|trade_execute|trade_close_positions|"
    r"goal_step_execute|supervis|credential|connect|trust|grant"
)


def _supports(kind: str, call: ToolCall, effect_tools: Collection[str]) -> bool:
    action = call.arguments.get("action")
    if kind == "card":
        return bool(_CARD_TOOLS.search(call.name))
    if kind == "stop":
        return call.name in {"trade_restriction_create", "owner_action_propose"}
    if kind == "resume":
        # Only the owner resumes trading; no tool result of this Run shows it resumed.
        return False
    if kind == "cancel":
        return bool(re.search(r"cancel|delete|remove|revoke|lift", call.name)) or (
            call.name == "trade_execute" and action in {"cancel_order", "close_position"}
        )
    if kind == "close":
        return call.name == "trade_close_positions" or (
            call.name == "trade_execute" and action == "close_position"
        )
    return call.name in effect_tools and not (
        call.name == "trade_execute" and action in ENTRY_ACTIONS
    )


_UNCERTAIN = {"tool_execution_uncertain", "broker_result_ambiguous"}


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
    statuses = [cast(dict[str, Any], row).get("status") for row in listed if isinstance(row, dict)]
    if result.get("code") in _UNCERTAIN or "ambiguous" in statuses:
        return "uncertain"
    if result.get("ok") is False or any(s in {"failed", "rejected"} for s in statuses):
        return "failed"
    return "confirmed"


def _support(
    state: dict[str, Any], messages: list[ModelMessage], kind: str, effect_tools: Collection[str]
) -> str:
    """The best outcome among this request's calls that would support the claim kind."""
    request = _request_messages(state, messages)
    calls = {c.id: c for m in request for c in m.tool_calls if _supports(kind, c, effect_tools)}
    outcomes = {
        _outcome(m.content) for m in request if m.role == "tool" and m.tool_call_id in calls
    }
    return next((o for o in ("confirmed", "uncertain") if o in outcomes), "failed")


@dataclass(frozen=True)
class ClaimVerdict:
    nudge: str | None = None
    # One honest line appended to the reply; the reply and its card are kept.
    appended: str | None = None

    @property
    def passed(self) -> bool:
        return self.nudge is None and self.appended is None


CLAIM_NUDGE = (
    "Your reply says an action was carried out, but no successful tool result in this "
    "request confirms it. This check is Lonora's, not the owner's, and the owner has not "
    "read your draft: write the reply afresh, with no apology and no mention of this check. "
    "Either do it now with the right tool, or tell the owner plainly what is not confirmed "
    "and ask if something is missing. Owner controls are tools reached with tool_call when "
    "not native: a pause or no new trades is trade_restriction_create; resuming trading, "
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


def _verdict(
    state: dict[str, Any], messages: list[ModelMessage], text: str, effect_tools: Collection[str]
) -> tuple[bool, bool]:
    """``(unsupported, uncertain)`` for the reply's claims in this owner request."""
    words = owner_words(state)
    if not words or not action_requested(words):
        return False, False
    outcomes = [_support(state, messages, kind, effect_tools) for kind in claim_kinds(text)]
    if not outcomes or all(o == "confirmed" for o in outcomes):
        return False, False
    return True, "uncertain" in outcomes


def claim_gate(
    state: dict[str, Any],
    messages: list[ModelMessage],
    text: str,
    effect_tools: Collection[str],
) -> ClaimVerdict:
    """One repair turn for an unsupported claim, then one appended honest line.

    An uncertain outcome is never repaired (a repair could resend it): the line says
    it is being checked. The counter lives in the checkpoint and resets only on real
    owner input (``reset_stop_gate``), so restarts cannot buy more attempts.
    """
    unsupported, uncertain = _verdict(state, messages, text, effect_tools)
    if not unsupported:
        return ClaimVerdict()
    if not uncertain and state.get(_STATE_KEY) != 1:
        state[_STATE_KEY] = 1
        return ClaimVerdict(nudge=CLAIM_NUDGE)
    return ClaimVerdict(appended=_line(owner_words(state), uncertain))


def unconfirmed_line(
    state: dict[str, Any], messages: list[ModelMessage], text: str, effect_tools: Collection[str]
) -> str | None:
    """The appended line for a reply no repair can follow (the tool-less final report)."""
    unsupported, uncertain = _verdict(state, messages, text, effect_tools)
    return _line(owner_words(state), uncertain) if unsupported else None


# --- D5: no program as a deliverable ---------------------------------------------------

_LANGUAGE = re.compile(
    r"\b(?:mql4|mql5|pine\s*script|pinescript|pine|python|javascript|typescript|c\+\+|c#|"
    r"java|lua|rust|golang|bash|powershell|vba|ninjascript|easylanguage|afl)\b|"
    r"بايثون|جافا|بلغه\s+\S+"
)
_DELIVERABLE = re.compile(
    _W + r"(?:ال)?(?:كود|سكربت|سكريبت|برنامج|مءشر|استراتيجيه|روبوت|اكسبرت|اكسبيرت)"
    r"|\b(?:code|script|program|indicator|strategy|bot|ea|expert\s+advisor)\b"
)
_ADVISOR = re.compile(_W + r"(?:ال)?(?:اكسبرت|اكسبيرت)|\bexpert\s+advisor\b|\bea\b")
_WRITE = re.compile(
    _W + r"(?:اكتب|ابن|ابني|اعمل|سوي|برمج)|\b(?:write|build|make|create|code|give)\b"
)


def code_requested(words: str) -> bool:
    """The owner asked for a program in a programming language (or an expert advisor)."""
    plain = _normalized(words)
    if _LANGUAGE.search(plain) and _DELIVERABLE.search(plain):
        return True
    return bool(_ADVISOR.search(plain) and _WRITE.search(plain))


_FENCE = re.compile(
    r"(?ms)^(?P<mark>```|~~~)(?P<lang>[^\n]*)\n(?P<body>.*?)(?:^(?P=mark)[ \t]*$|\Z)"
)


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

    Display fences and short explanation blocks (Q36) stay; the rest of the reply stays.
    """
    if not code_requested(words):
        return text
    declined = False

    def replace(match: re.Match[str]) -> str:
        nonlocal declined
        language = match.group("lang").strip().lower()
        lines = sum(1 for line in match.group("body").splitlines() if line.strip())
        if language in _DISPLAY_FENCES or lines < DELIVERABLE_LINES:
            return match.group(0)
        first, declined = not declined, True
        return code_decline(words) + "\n" if first else ""

    return _FENCE.sub(replace, text)
