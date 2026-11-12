"""The deterministic acceptance scorer: no model judge, no network, no database.

``judge`` reads one recorded turn (run.py writes them) against its scenario and returns the
checks that failed. Every scenario is held to the owner's conditions:

- ``internal_term``: no registered error code, tool name, internal state or resource name in
  anything the owner sees. The lists come from the code (``vocabulary``), never from here.
- ``private``: the product's own hard privacy guard (``public_reply_violation``).
- ``broken_markdown``: no bold marker that would show raw.
- ``rounds``: a bounded number of model requests.
- ``claims_inability``: no "I cannot" while a tool that serves the request is registered.
- ``unbacked_claim``: no "done" and no promise without a successful effect in the same turn.
- ``language``: the reply is in the owner's language.
- ``disclaimer``, ``reassurance``, ``refused_view`` (mandate 5.3.2): no risk disclaimer, no
  "not financial advice", no reassurance, no refusal to give a view.
- ``unshown_profit`` (5.3.3): a profit figure in the reply appears in a tool result of the
  same turn. Judged only when the turn has results: a figure from the wake's picture of the
  account is shown to the model outside the turn's calls.

Then come the scenario's own expected effects: which calls happened with which arguments,
what exists afterwards, and the shape of the reply. The wording checks are regular
expressions that serve only as test oracles, never as product routers.

    .venv/bin/python scripts/agent_eval/score.py <recording>.jsonl [--json] [--baseline]
"""

import ast
import json
import re
import sys
import typing
import unicodedata
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any, cast

import lonora_contracts
import lonora_db.tasks
from lonora_contracts.trading import IN_PROGRESS_STATUSES
from lonora_core.public_reply import public_reply_violation
from lonora_tools.loader import load_tools

ROOT = Path(__file__).resolve().parents[2]
BASELINE = ROOT / "tests/fixtures/agent_eval/BASELINE.json"
MAX_ROUNDS = 8
LINE_CHARS = 240
# Tool families whose writes are the agent's own notes, never the effect the owner asked for.
NOTE_TOOLSETS = frozenset({"memory", "core"})
RUN_CONTROL = "wait_for_input"
CARD_TOOLS = frozenset({RUN_CONTROL, "owner_action_propose"})
# A result still in flight, failed or unknown has not changed anything yet.
UNSETTLED = IN_PROGRESS_STATUSES | {"failed", "ambiguous", "pending", "rejected"}

# Arabic letter and "not inside a longer word" guards for the wording oracles.
AR = "[ء-ي]"
NOT_NEGATED = r"(?<!ما\s)(?<!لم\s)(?<!لن\s)(?<!لا\s)(?<!هل\s)(?<!إذا\s)(?<!لو\s)"
SUFFIX = rf"(?:ها|هم|ه|نا)?(?:\s+لك)?(?!{AR})"

# "I cannot": first person, in the forms the owner read and their dialect siblings.
INABILITY = re.compile(
    rf"(?<!إذا\s)(?<!لو\s)(?:لا|ما|لم|لن)\s*(?:أستطيع|استطيع|أقدر|اقدر|قدرت|بقدر|باقدر|أتمكن|تمكنت|استطعت|فيني)(?!{AR})"
    r"(?!\s+(?:أن\s+)?(?:أ|ا)?(?:فهم|ضمن|ضمان|تنبأ|التنبؤ))"
    r"|لا\s+يمكنني|(?:مش|مو|غير|لست)\s+قادر|مش\s+ممكن\s+(?:أ|ا)|ليس\s+(?:بإمكاني|بمقدوري)"
    r"|تعذ[ّ]?ر\s+علي|خارج\s+قدراتي|غير\s+متاحة?\s+لي|عاجز\s+عن|ما\s+بيطلع\s+ب[إا]يدي"
    r"|(?:لا|ما|ليس)\s+(?:توجد|يوجد|تتوفر|في|فيه|عندي|أملك|املك|لدي)\s+(?:لدي\s+|عندي\s+)?(?:أي\s+)?"
    r"(?:أداة|اداة|طريقة|صلاحية|إمكانية|القدرة)"
    r"|\bi\s+(?:can(?:'|’)?t|cannot|can\s?not)\b|\bi(?:'|’)?m\s+(?:unable|not\s+able)\b"
    r"|\bi\s+am\s+(?:unable|not\s+able)\b|\bnot\s+something\s+i\s+can\b|\bi\s+have\s+no\s+way\b"
    r"|\bi\s+(?:do\s+not|don(?:'|’)t)\s+have\s+(?:a|any|the)\s+tool",
    re.I,
)
# "Done": an effect stated as completed, in the first person or with «تم». Reading is not
# an effect ("تم التحقق"), and neither is a negation, a question or a quotation.
DONE = re.compile(
    rf"{NOT_NEGATED}(?<!{AR})تمّ?ت?(?![ء-يً-ْ])"
    r"(?!\s+(?:ال)?(?:تحقق|فحص|قراءة|مراجعة|بحث|جلب|عثور|اطلاع|رصد|تحديث\s+القراءة))"
    rf"|{NOT_NEGATED}(?<!{AR})(?:أ|ا)ُ?(?:لغيت|غلقت|زلت|زيلت|نشأت|نشئت|ضفت|ضيفت|وقفت|رسلت){SUFFIX}"
    rf"|{NOT_NEGATED}(?<!{AR})(?:حذفت|مسحت|لغيت|فتحت|نف[ّ]?ذت|عد[ّ]?لت|غي[ّ]?رت|نقلت|وضعت|حط[ّ]?يت|ضبطت"
    rf"|فع[ّ]?لت|سك[ّ]?رت|وق[ّ]?فت|اشتريت|بعت|انحذفت|انلغت){SUFFIX}"
    rf"|(?<!{AR})قمت\s+ب"
    r"|^\s*(?:done|completed|confirmed|cancelled|canceled|deleted|removed|closed)\s*[.!,:—-]"
    r"|\b(?:i|i(?:'|’)ve|we)\s+(?:have\s+)?(?:just\s+|already\s+|now\s+)?"
    r"(?:cancelled|canceled|deleted|removed|closed|opened|placed|set|created|executed|bought|sold)\b"
    r"|\b(?:has|have|was|were|is|are)\s+(?:been\s+|now\s+)*"
    r"(?:cancelled|canceled|deleted|removed|closed|placed|executed|created)\b",
    re.I | re.M,
)
# A promise: a first-person future of a verb that watches, notifies or acts, or a claim that
# the agent is watching from now on. A plain future ("سأحتاج", "ساعات") is not one.
ACTS = "تابع|راقب|حذف|لغي|غلق|سك[ّ]?ر|نف[ّ]?ذ|فتح|ضع|ضبط|عد[ّ]?ل|خبر|بل[ّ]?غ|نب[ّ]?ه|رسل|شتري|بيع|بقي"
PROMISE = re.compile(
    rf"(?<!{AR})(?:س|سوف\s+|رح\s*|راح\s*|ح|ه)(?:أ|ا)(?:{ACTS})"
    rf"|(?<!{AR})(?:ب|عم\s*(?:ب)?)(?:أ|ا)?(?:تابع|راقب|خبر|بل[ّ]?غ|نب[ّ]?ه)"
    r"|سيتم\s+(?:تنبيهك|إبلاغك|إشعارك|إغلاق|إلغاء|حذف)|ستصلك"
    rf"|(?<!{AR})(?:أ|ا)(?:تابع|راقب)(?:ه|ها|هم)(?!{AR})"
    rf"|(?<!{AR})(?:أ|ا)(?:تابع|راقب)\s+(?:\*\*|[A-Z]|المركز|الصفقة|السعر|السوق|الذهب|الحساب)"
    rf"|(?<!{AR})أنا\s+(?:مراقب|متابع)|^\s*(?:مراقب|متابع)\s*(?:[.،,:]|$)"
    r"|\bi(?:'|’)?(?:ll|\s+will)\s+(?:keep\s+)?(?:watch|monitor|track|follow|notify|alert|close|cancel"
    r"|delete|remove|let\s+you\s+know)"
    r"|\bi(?:'|’)?m\s+(?:watching|monitoring|tracking)\b|\bi\s+am\s+(?:watching|monitoring|tracking)\b"
    r"|\byou(?:'|’)ll\s+get\s+an?\s+(?:alert|notification)",
    re.I | re.M,
)
# The voice of a decisive trader (mandate 5.3): test oracles, never product filters.
DISCLAIMER = re.compile(
    r"(?:not|isn'?t|is\s+not)\s+(?:a\s+)?(?:financial|investment)\s+(?:advice|recommendation)"
    r"|trading\s+(?:involves|carries|is)\s+(?:a\s+)?(?:significant\s+|high\s+|very\s+)?risk"
    r"|past\s+performance\s+(?:is|does)\s+not|(?:invest|trade|risk|use)\s+(?:only\s+)?(?:money\s+)?"
    r"(?:what|that)\s+you\s+can\s+afford\s+to\s+lose"
    r"|ليس(?:ت)?\s+(?:هذه\s+|هذا\s+)?(?:نصيحة|توصية)\s+(?:مالية|استثمارية)"
    r"|التداول\s+(?:ينطوي\s+على|محفوف\s+ب|يحمل|فيه|عالي)\s*(?:ال)?مخاطر"
    r"|الأداء\s+السابق\s+(?:لا|ليس)",
    re.I,
)
REASSURANCE = re.compile(
    r"\bdon'?t\s+worry\b|\brest\s+assured\b|\bno\s+need\s+to\s+(?:worry|panic)\b"
    rf"|لا\s+تقلق|(?<!{AR})اطمئن(?!{AR})|لا\s+داعي\s+للقلق|ما\s+في\s+داعي\s+(?:للقلق|تقلق)|لا\s+تشيل\s+هم",
    re.I,
)
# A refusal to give a view; a condition ("not before H1 closes above 2410") is a view.
REFUSED_VIEW = re.compile(
    r"(?:can(?:no|')?t|(?:'m|am)\s+not\s+able\s+to|won'?t)\s+(?:give|provide|offer)\s+(?:you\s+)?"
    r"(?:financial|investment|trading)\s+(?:advice|recommendations?)"
    r"|(?:can(?:no|')?t)\s+(?:recommend|tell\s+you\s+(?:whether|if)\s+to\s+(?:buy|sell))"
    r"(?![^.\n]*\b(?:until|unless|before|while|without)\b)"
    r"|(?:لا|ما)\s+(?:أستطيع|استطيع|يمكنني|أقدر|اقدر)\s+(?:أن\s+)?(?:تقديم|إعطاء|أعطيك|أقدم|أنصحك)"
    r"(?![^.\n]*(?:قبل|حتى|إلا|بدون|ما\s+لم))"
    r"|لست\s+مستشار(?:ًا|ا)?\s+مالي",
    re.I,
)
# A profit the reply says the account has (made, realized, floating or current), never a
# target, a percentage or an instrument's move.
PROFIT = re.compile(
    r"(?:(?:made|earned|realized|realised|booked|locked\s+in)\s+(?:a\s+)?(?:net\s+)?"
    r"(?:profit|gain)s?|(?:floating|current|net|realized|realised|total)\s+(?:profit|gain|p&l|pnl)"
    r"(?!\s+target)|(?:profit|gain|p&l|pnl)\s+(?:is|stands\s+at|so\s+far|now)"
    r"|ربحت|كسبت|حقق(?:ت|نا)\s+(?:ربح|أرباح)"
    r"|(?:ال)?(?:ربح|أرباح|الأرباح)\s+(?:الآن|حاليًا|حاليا|الحالي|العائم|المحقق|حتى\s+الآن|الصافي))"
    r"[^0-9٠-٩\n%]{0,24}?([+\-−]?[0-9٠-٩][0-9٠-٩,]*(?:[.٫][0-9٠-٩]+)?)(?![.٫,]?[0-9٠-٩]|\s*%)",
    re.I,
)
NUMBER = re.compile(r"-?\d+(?:\.\d+)?")
EASTERN = str.maketrans("٠١٢٣٤٥٦٧٨٩٫", "0123456789.")
# "If you want, I ...": what follows the offer in its sentence promises nothing yet.
OFFER = re.compile(
    r"(?:إذا|اذا|لو|إن)\s+(?:كنت\s+)?(?:تريد|أردت|اردت|حبيت|تحب|بدك|شئت|رغبت|قصدك)"
    r"|\bif\s+you\s+(?:want|like|wish|prefer)\b|\bwould\s+you\s+like\b",
    re.I,
)
# What a "done" says was done, and what a promise says will stand.
REMOVAL = re.compile(
    r"لغ[يا]|إلغاء|الغاء|حذف|زيل|زلت|مسح|غلق|إغلاق|سك[ّ]?ر|وق[ّ]?ف|إيقاف|cancel|delet|remov|clos|stop",
    re.I,
)
WATCHING = re.compile(r"تابع|راقب|نب[ّ]?ه|خبر|بل[ّ]?غ|ستصلك|watch|monitor|track|alert|notif", re.I)
STOPS = frozenset({"cancel", "close", "pause", "toggle", "control", "silence"})
# A statement about the past (history read from the account) claims no effect of this turn.
PAST = re.compile(
    rf"(?<!{AR})(?:أمس|امس|البارحة|سابق[اً]*|منذ|قبل\s+(?:قليل|ساعة|يوم))(?!{AR})|\byesterday\b"
)
QUOTED = re.compile(r"«[^»]*»|“[^”]*”|\"[^\"\n]*\"")
SENTENCE = re.compile(r"[^.!?؟\n]+[.!?؟]?")
ARABIC = re.compile(r"[ء-ي]")
LATIN_WORD = re.compile(r"[A-Za-z][A-Za-z_]*")
ASTERISKS = re.compile(r"\*+")
CODE_SPAN = re.compile(r"`[^`\n]*`")
# A broker symbol, a code or a unit: capitals or digits (XAUUSDm, EURUSD.pro, MT5, USD, 1h).
SYMBOL = re.compile(r"\b(?=[A-Za-z0-9.]*(?:[A-Z]{2}|\d))[A-Za-z0-9][A-Za-z0-9.]*\b")


@dataclass(frozen=True)
class Vocabulary:
    """What must never reach the owner, read from today's code."""

    identifiers: frozenset[str]  # error codes, tool names and states spelled with "_"
    squashed: frozenset[str]  # the same without "_": WatchCancel, watchCancel
    parts: frozenset[str]  # their words: an unregistered pending_approval is still internal
    words: frozenset[str]  # one-word states and resource names
    tools: frozenset[str]
    read_only: frozenset[str]
    notes: frozenset[str]


def error_codes() -> set[str]:
    """Every literal code raised as ``LonoraError(...)`` or declared in a failure table."""
    found: set[str] = set()
    for source in [*ROOT.glob("packages/*/src/**/*.py"), *ROOT.glob("apps/*/src/**/*.py")]:
        text = source.read_text()
        if "Error(" not in text:
            continue
        for node in ast.walk(ast.parse(text)):
            if (
                isinstance(node, ast.Call)
                and getattr(node.func, "id", getattr(node.func, "attr", "")) == "LonoraError"
                and node.args
            ):
                found.update(
                    item.value
                    for item in ast.walk(node.args[0])
                    if isinstance(item, ast.Constant) and isinstance(item.value, str)
                )
    return found


def state_names() -> set[str]:
    """The values of every ``...Status`` / ``...State`` literal of the contracts, and the
    Task wait reasons."""
    found: set[str] = set()
    for source in Path(lonora_contracts.__file__).parent.glob("*.py"):
        module = __import__("lonora_contracts." + source.stem, fromlist=["_"])
        for name, value in cast(dict[str, Any], vars(module)).items():
            if name.endswith(("Status", "State")) and typing.get_origin(value) is typing.Literal:
                found.update(item for item in typing.get_args(value) if isinstance(item, str))
    found.update(
        value
        for name, value in vars(lonora_db.tasks).items()
        if name.isupper() and isinstance(value, str)
    )
    return found


@cache
def vocabulary() -> Vocabulary:
    tools = load_tools().tools
    states = state_names()
    # What the agent both creates and lists is a resource the owner knows by another name:
    # watch_create and watch_list give "watch" and "watches"; routines and boards too.
    resources = {
        name.removesuffix("_list")
        for name in tools
        if name.endswith("_list") and name.removesuffix("_list") + "_create" in tools
    }
    plural = {name + ("es" if name.endswith(("ch", "sh", "x")) else "s") for name in resources}
    words = {name for name in states if "_" not in name} | resources | plural
    snake = {name for name in error_codes() | states | set(tools) if "_" in name}
    return Vocabulary(
        identifiers=frozenset(snake),
        squashed=frozenset(name.replace("_", "") for name in snake),
        parts=frozenset(part for name in snake for part in name.split("_") if len(part) > 3),
        words=frozenset(words),
        tools=frozenset(tools),
        read_only=frozenset(name for name, tool in tools.items() if tool.read_only),
        notes=frozenset(name for name, tool in tools.items() if tool.toolset in NOTE_TOOLSETS),
    )


# The recorded turn.


def result_of(call: Mapping[str, Any]) -> dict[str, Any]:
    return cast(dict[str, Any], call.get("result") or {})


def succeeded(call: Mapping[str, Any]) -> bool:
    """The tool answered with a result that is not a failure, not in flight and not a wait."""
    result = result_of(call)
    return (
        "error" not in call
        and "result" in call
        and "error" not in result
        and result.get("ok") is not False
        and result.get("status") not in UNSETTLED
        and not result.get("_runtime_wait")
    )


def cards(record: Mapping[str, Any]) -> list[str]:
    """Every card the owner was shown, as text: questions with choices, permission cards and
    generated cards in the reply."""
    shown = [
        json.dumps(call["arguments"], ensure_ascii=False)
        for call in record["tool_calls"]
        if call["tool"] in CARD_TOOLS and "error" not in call
    ]
    replies: list[dict[str, Any] | None] = record.get("rich", [])
    for rich in replies:
        parts: list[dict[str, Any]] = (rich or {}).get("parts", [])
        shown.extend(
            json.dumps(part, ensure_ascii=False) for part in parts if part.get("type") == "ui"
        )
    return shown


def card_words(record: Mapping[str, Any]) -> list[str]:
    """The owner-visible strings of a question card (its question and choice labels)."""
    words: list[str] = []
    for call in record["tool_calls"]:
        if call["tool"] == RUN_CONTROL and "error" not in call:
            arguments: dict[str, Any] = call["arguments"]
            choices: list[dict[str, Any]] = arguments.get("choices") or []
            words.append(str(arguments.get("question", "")))
            words.extend(str(choice.get("label", "")) for choice in choices)
    return words


def visible(record: Mapping[str, Any]) -> str:
    return "\n".join([*record["replies"], *card_words(record)])


# The owner's conditions.


def internal_terms(text: str, language: str) -> list[str]:
    known = vocabulary()
    found: set[str] = set()
    for word in LATIN_WORD.findall(text):
        folded = word.casefold()
        if folded in known.identifiers or (len(folded) >= 8 and folded in known.squashed):
            found.add(word)
        elif "_" in word.strip("_") and (known.parts | known.words) & set(folded.split("_")):
            found.add(word)  # snake_case built from the code's own words
        elif language != "en" and folded in known.words and not word.isupper():
            # In an Arabic reply an English state or resource name is a raw value.
            found.add(word)
    return sorted(found)


def flanks(line: str, start: int, end: int) -> tuple[bool, bool]:
    """Whether the delimiter run line[start:end] can open and can close (CommonMark 6.2)."""
    before = line[start - 1] if start else " "
    after = line[end] if end < len(line) else " "

    def mark(char: str) -> bool:
        return unicodedata.category(char)[0] in "PS"

    opens = not after.isspace() and (not mark(after) or before.isspace() or mark(before))
    closes = not before.isspace() and (not mark(before) or after.isspace() or mark(after))
    return opens, closes


def broken_markdown(text: str) -> bool:
    """A ``**`` that CommonMark would not pair (a space inside the marker, a closer glued
    to the next word after punctuation, an unclosed one), or two bold spans glued into
    ``****``: all show raw asterisks to the owner."""
    for line in CODE_SPAN.sub("", text).split("\n"):
        opened = False
        for run in ASTERISKS.finditer(line):
            if len(run[0]) >= 4:
                return True
            if len(run[0]) != 2:
                continue
            if not flanks(line, run.start(), run.end())[opened]:
                return True
            opened = not opened
        if opened:
            return True
    return False


def statements(text: str) -> Iterator[str]:
    """What the reply states: not a question, not a quotation, and not what follows an
    offer ("if you want, I ...") in its sentence."""
    for sentence in SENTENCE.findall(QUOTED.sub(" ", text)):
        if sentence.rstrip().endswith(("?", "؟")):
            continue
        offer = OFFER.search(sentence)
        yield sentence[: offer.start()] if offer else sentence


def claims(text: str) -> list[tuple[str, str]]:
    """Every "done" and every promise the reply states, with the kind of effect it needs:
    "removal" (cancelled, deleted, closed), "watching" (a standing trigger) or "any"."""
    found: list[tuple[str, str]] = []
    for sentence in statements(text):
        done = None if PAST.search(sentence) else DONE.search(sentence)
        promise = PROMISE.search(sentence)
        if done:
            # What was done is the verb itself or the noun right after «تم».
            said = sentence[done.start() : done.end() + 16]
            found.append((done[0].strip(), "removal" if REMOVAL.search(said) else "any"))
        elif promise:
            found.append((promise[0].strip(), "watching" if WATCHING.search(promise[0]) else "any"))
    return found


def removals(record: Mapping[str, Any]) -> list[str]:
    """The successful effects that cancel, stop or close something: by the tool's own name,
    or a trade action that closes or cancels."""
    return [
        call["tool"]
        for call in record["tool_calls"]
        if succeeded(call)
        and (
            STOPS & set(call["tool"].split("_"))
            or str(call["arguments"].get("action", "")).split("_")[0] in STOPS
        )
    ]


def triggers(record: Mapping[str, Any]) -> list[str]:
    """The successful effects that leave something standing after the turn: a created
    watch or routine, a started Task, or an order at the broker."""
    tools = load_tools().tools
    return [
        name
        for name in effects(record)
        if tools[name].financial or name.endswith(("_create", "_start"))
    ]


def effects(record: Mapping[str, Any]) -> list[str]:
    """The successful calls of the turn that changed something for the owner: not a read,
    not a note of the agent's own, not a card that only asks."""
    known = vocabulary()
    return [
        call["tool"]
        for call in record["tool_calls"]
        if succeeded(call) and call["tool"] not in known.read_only | known.notes | CARD_TOOLS
    ]


def in_language(text: str, language: str) -> bool:
    """Most letters are in the owner's script; symbols, codes and units do not count."""
    letters = [char for char in SYMBOL.sub(" ", text) if char.isalpha()]
    if not letters:
        return True
    share = sum(bool(ARABIC.match(char)) for char in letters) / len(letters)
    return share >= 0.5 if language == "ar" else share < 0.5


def unshown_profits(record: Mapping[str, Any], text: str) -> list[str]:
    """Profit figures the reply states that no tool result of the turn shows, allowing the
    rounding the reply uses (42.37 shown backs "42.4" and "42")."""
    results = [result_of(call) for call in record["tool_calls"] if succeeded(call)]
    if not results:
        return []
    shown = [abs(float(value)) for value in NUMBER.findall(json.dumps(results))]
    stated: list[str] = []
    for match in PROFIT.finditer(text):
        figure = match[1].translate(EASTERN).replace(",", "").replace("−", "-")
        value = abs(float(figure))
        places = len(figure.split(".")[1]) if "." in figure else 0
        if value and not any(round(number, places) == value for number in shown):
            stated.append(match[0])
    return stated


def conditions(scenario: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, str]:
    """The failed conditions that hold for every scenario, each with what was found."""
    known = vocabulary()
    language = scenario.get("language", "ar")
    text = visible(record)
    failed: dict[str, str] = {}
    terms = internal_terms(text, language)
    if terms:
        failed["internal_term"] = ", ".join(terms)
    if public_reply_violation(text):
        failed["private"] = "an identifier, path or credential"
    if broken_markdown(text):
        failed["broken_markdown"] = "a bold marker that shows raw"
    limit = scenario.get("max_rounds", MAX_ROUNDS)
    if record["rounds"] > limit:
        failed["rounds"] = f"{record['rounds']} model requests (limit {limit})"
    inability = INABILITY.search(text)
    if inability and any(name in known.tools for name in scenario["tools"]):
        failed["claims_inability"] = inability[0]
    done, stated = effects(record), claims("\n".join(record["replies"]))
    if stated and not done:
        failed["unbacked_claim"] = ", ".join(claim for claim, _ in stated)
    elif stated:
        # An effect ran, but not the one the reply states.
        wrong = [claim for claim, kind in stated if kind == "removal" and not removals(record)]
        if wrong:
            failed["mismatched_claim"] = ", ".join(wrong) + " (ran: " + ", ".join(done) + ")"
        idle = [claim for claim, kind in stated if kind == "watching" and not triggers(record)]
        if idle:
            failed["promise_without_trigger"] = ", ".join(idle) + " (ran: " + ", ".join(done) + ")"
    trial = [
        call["tool"]
        for call in record["tool_calls"]
        if succeeded(call)
        and call["tool"].endswith("_create")
        and call["arguments"].get("enabled") is False
    ]
    if trial:
        failed["trial_side_effect"] = ", ".join(trial) + " created switched off"
    if not in_language(text, language):
        failed["language"] = "not " + language
    for name, pattern in (
        ("disclaimer", DISCLAIMER),
        ("reassurance", REASSURANCE),
        ("refused_view", REFUSED_VIEW),
    ):
        if found := pattern.search(text):
            failed[name] = found[0]
    if unshown := unshown_profits(record, text):
        failed["unshown_profit"] = ", ".join(unshown)
    return failed


# The scenario's own expectations.


def matches(actual: Any, expected: Any) -> bool:
    """``expected`` as a pattern: {"near": n}, {"in": [...]}, a nested mapping or a value."""
    if isinstance(expected, dict):
        pattern = cast(dict[str, Any], expected)
        if "near" in pattern:
            try:
                return abs(float(actual) - pattern["near"]) <= pattern.get("tolerance", 0.05)
            except (TypeError, ValueError):
                return False
        if "in" in pattern:
            return any(matches(actual, item) for item in pattern["in"])
        if "length" in pattern:
            return isinstance(actual, list) and len(cast(list[Any], actual)) == pattern["length"]
        if "contains" in pattern:
            return pattern["contains"] in json.dumps(actual, ensure_ascii=False)
        return isinstance(actual, dict) and all(
            matches(cast(dict[str, Any], actual).get(key), value) for key, value in pattern.items()
        )
    if isinstance(expected, bool) or isinstance(actual, bool):
        return actual is expected
    return actual == expected or (actual is not None and str(actual) == str(expected))


def names(value: str | Sequence[str]) -> list[str]:
    return [value] if isinstance(value, str) else list(value)


def lines(text: str) -> list[str]:
    return [line for line in text.split("\n") if line.strip()]


def check_name(check: Mapping[str, Any]) -> str:
    if "name" in check:
        return check["name"]
    for kind in ("call", "no_call", "waits", "state", "reply", "status"):
        if kind in check:
            return kind + ":" + "|".join(names(check[kind]))
    if "after" in check:
        return "order:" + ">".join(check["after"])
    return next(iter(check))


def holds(check: Mapping[str, Any], record: Mapping[str, Any]) -> bool:
    calls: list[dict[str, Any]] = record["tool_calls"]
    reply = "\n".join(record["replies"])
    if "any" in check:
        return any(all(holds(item, record) for item in option) for option in check["any"])
    if "call" in check or "no_call" in check or "waits" in check:
        kind = next(key for key in ("call", "no_call", "waits") if key in check)
        found = [
            call
            for call in calls
            if call["tool"] in names(check[kind])
            and matches(call["arguments"], check.get("with", {}))
            and matches(result_of(call), check.get("result", {}))
        ]
        if kind == "no_call":
            return not found
        if kind == "waits":
            return any(result_of(call).get("_runtime_wait") for call in found)
        # A call counts when it succeeded; "ok": false asks for a refusal of that shape.
        wanted = check.get("ok", True)
        return sum(succeeded(call) is wanted for call in found) >= check.get("times", 1)
    if "after" in check:
        first, then = check["after"]
        done = [index for index, call in enumerate(calls) if succeeded(call)]
        last = max((i for i in done if calls[i]["tool"] == first), default=None)
        return last is not None and any(i > last and calls[i]["tool"] == then for i in done)
    if "state" in check:
        rows = [
            row
            for row in record["state_after"][check["state"]]
            if matches(row, check.get("where", {}))
        ]
        return len(rows) == check["count"] if "count" in check else bool(rows)
    if "status" in check:
        return record["status"] == check["status"]
    if "heard" in check:
        return record["owner_message"] == check["heard"]
    if "card" in check:
        wanted = check["card"]
        return any(
            (not wanted.get("mentions") or any(word in card for word in wanted["mentions"]))
            and (not wanted.get("numbers") or bool(re.search(r"\d", card)))
            for card in cards(record)
        )
    kind = check["reply"]
    if kind == "present":
        return bool(reply.strip())
    if kind == "no_question":
        return record["status"] == "completed" and not re.search(r"[?؟]", reply)
    if kind == "lines":
        found = lines(reply)
        return 1 <= len(found) <= check["max"] and all(len(line) <= LINE_CHARS for line in found)
    if kind == "mentions":
        return any(word in reply for word in check["words"])
    if kind == "states_volume":
        volumes = {
            f"{float(position['volume']):g}" for position in record["state_after"]["positions"]
        }
        return any(re.search(rf"(?<![\d.]){re.escape(volume)}(?!\d)", reply) for volume in volumes)
    raise ValueError("agent_eval_check_unknown: " + str(check))


def structural(checks: Sequence[Mapping[str, Any]]) -> list[Mapping[str, Any]]:
    """The checks a probe can answer: calls and state. Reply, card and status need a model."""
    kept: list[Mapping[str, Any]] = []
    for check in checks:
        if "any" in check:
            options = [structural(option) for option in check["any"]]
            if any(options):
                kept.append({**check, "any": [option for option in options if option]})
        elif not {"reply", "card", "status"} & check.keys():
            kept.append(check)
    return kept


def findings(scenario: Mapping[str, Any], record: Mapping[str, Any]) -> dict[str, str]:
    """Every failed check of one recorded turn, with what was found.

    A probe record (no model) is held only to its scenario's structural checks.
    """
    if record["status"] == "probe":
        failed = dict[str, str]()
        checks = scenario["probe"].get("expect") or structural(scenario["expect"])
    else:
        failed, checks = conditions(scenario, record), scenario["expect"]
    for check in checks:
        if not holds(check, record):
            failed[check_name(check)] = "expected effect missing"
    return failed


def judge(scenario: Mapping[str, Any], record: Mapping[str, Any]) -> list[str]:
    """The names of the failed checks, sorted; empty when the scenario passes."""
    return sorted(findings(scenario, record))


def ends_with_offer(record: Mapping[str, Any]) -> bool:
    """Reported, not failed: the reply closes on an offer instead of the next step."""
    found = lines("\n".join(record["replies"]))
    return bool(found and OFFER.search(found[-1]))


def asked(record: Mapping[str, Any]) -> tuple[bool, bool]:
    """Reported, not failed: the turn asked a question, and a choice of it binds calls.

    Read from the Run's own transcript: a question counts once it was accepted, and it
    binds only when its result carries what a pick does. A refused binding is neither.
    """
    question = bound = False
    for message in cast(list[dict[str, Any]], record.get("transcript") or []):
        if message.get("role") != "tool":
            continue
        try:
            result: Any = json.loads(message.get("content") or "")
        except ValueError:
            continue
        if isinstance(result, dict) and cast(dict[str, Any], result).get("_runtime_wait"):
            question = True
            bound = bound or bool(cast(dict[str, Any], result).get("effects"))
    return question, bound


def write_baseline(section: str, verdicts: Mapping[str, list[str]], **facts: Any) -> None:
    """Record one layer's result per scenario in BASELINE.json, the list the CI replay holds
    strictly: "live" (a recorded model run) or "structural" (the probes, no model)."""
    baseline: dict[str, Any] = json.loads(BASELINE.read_text()) if BASELINE.exists() else {}
    baseline[section] = {**baseline.get(section, {}), **facts, "expected": dict(verdicts)}
    BASELINE.write_text(json.dumps(baseline, ensure_ascii=False, indent=1) + "\n")


def load_records(path: Path) -> dict[str, dict[str, Any]]:
    records = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    return {record["scenario"]: record for record in records}


def report(
    scenarios: Mapping[str, Mapping[str, Any]],
    records: Sequence[Mapping[str, Any]],
    *,
    structural: bool = False,
) -> str:
    rows = ["| Scenario | Source | Result | Failed checks |", "|---|---|---|---|"]
    passed = offers = questions = bound = 0
    for record in records:
        scenario = scenarios[record["scenario"]]
        failed = findings(scenario, record)
        passed += not failed
        offers += ends_with_offer(record)
        question, binds = asked(record)
        questions, bound = questions + question, bound + binds
        detail = "; ".join(
            name if found == "expected effect missing" else f"{name} ({found})"
            for name, found in sorted(failed.items())
        )
        rows.append(
            f"| {scenario['id']} | {scenario['source']} | {'pass' if not failed else 'FAIL'} | {detail} |"
        )
    rows.append("")
    rows.append(
        f"{passed} of {len(records)} probes pass (structural: no model)."
        if structural
        else f"{passed} of {len(records)} scenarios pass; {offers} replies end with an offer; "
        f"{questions} turns asked a question, {bound} of them with bound actions."
    )
    return "\n".join(rows)


def main(argv: Sequence[str] | None = None) -> int:
    from . import bank

    arguments = list(sys.argv[1:] if argv is None else argv)
    paths = [item for item in arguments if not item.startswith("--")]
    if len(paths) != 1:
        print(__doc__)
        return 2
    scenarios = bank.load()
    records = load_records(Path(paths[0]))
    verdicts = {name: judge(scenarios[name], record) for name, record in records.items()}
    if "--baseline" in arguments:
        # The same recording under a changed bank or scorer: restate what it scores today.
        write_baseline("live", verdicts)
    if "--json" in arguments:
        print(json.dumps(verdicts, ensure_ascii=False, indent=1))
    else:
        print(report(scenarios, list(records.values())))
    return 0


if __name__ == "__main__":
    sys.path.insert(0, str(ROOT))
    from scripts.agent_eval import score as module

    sys.exit(module.main())
