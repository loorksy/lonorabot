"""Compile a lonora-ui v2 card against this request's evidence (docs/genui.md).

Deterministic repair only (no second model call): facts resolve from this request's
successful tool results; the card has one account, the account of its first
account-bearing fact; asset options are exact broker symbols read this turn on that account
and labelled with the server's names; sends use only listed, non-financial intents; the
server inserts the read-only delivery row; the budget folds or falls back. A failure that
would leave a half-built form raises ``CardError`` and the reply shows the card's fallback.
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage
from lonora_contracts.genui import (
    INPUTS,
    SLOT,
    TEXT_CAPS,
    CardError,
    Diagnostics,
    ParsedCard,
    UiDocument,
    walk,
)
from lonora_contracts.genui_expr import environment, evaluate, references, render_template, show
from lonora_contracts.genui_intents import REGISTRY, intent_denied
from lonora_contracts.instrument_names import known_names
from lonora_core.public_reply import public_reply_violation, redact_private_reply
from lonora_core.search_fold import fold

from .context.financial_result import FINANCIAL_CALLS
from .genui_capabilities import UiCapabilities

PRIVATE_KEY = re.compile(
    r"password|secret|token|credential|private.?key|authorization|api.?key|access.?key|signing.?key|recovery.?code",
    re.I,
)
FAILED = {"error", "failed", "denied", "unavailable", "rejected"}
DECIMAL = re.compile(r"^-?\d+(?:\.\d+)?$")
UNBOUND = re.compile(r"\{\{\s*[A-Za-z_][\w.]*\s*\}\}")
# Every node prop a client displays (a Slider's readout too); a copy action's text is read the
# same way, since it reaches the clipboard and, when that fails, the card's notice.
DISPLAYED = ("label", "text", "hint", "sub", "value", "title", "suffix", "prefix", "show")


def copy_text(node: dict[str, Any]) -> str | None:
    action = node.get("action")
    if isinstance(action, dict) and cast(dict[str, Any], action).get("do") == "copy":
        text = cast(dict[str, Any], action).get("text")
        return text if isinstance(text, str) else None
    return None


MAX_COLUMN = 100
MAX_OBJECT_SCALARS = 300
SYMBOL_TOOLS = {"market_quote", "market_instrument"}
RESTING_LIMIT = 560
HARD_LIMIT = 720
DEFAULT_WHY = {
    "form": "نموذج قصير يجمع ما يحتاجه الطلب مرة واحدة ويمنع الأخطاء، بدل أسئلة متتالية.",
    "calculator": "حاسبة تفاعلية تجرّب فيها الأرقام بنفسك وترى النتيجة فورًا؛ أوضح من شرح نصي.",
    "diagram": "مستويات وأسهم تُظهر كيف تتصل الأجزاء في نظرة واحدة، أوضح من فقرات.",
    "summary": "ملخص قصير بالتفاصيل مع زر للخطوة التالية؛ أوضح من فقرة وأسهل من البحث في القوائم.",
}
HEIGHTS = {
    "Segmented": 68,
    "Number": 70,
    "Select": 70,
    "Slider": 54,
    "Text": 20,
    "Note": 40,
    "Stat": 64,
    "Button": 40,
    "Delivery": 62,
    "Divider": 13,
    "Title": 26,
    "Markdown": 60,
    "Badge": 24,
    "More": 40,
}
# A trusted slot's height at rest at 390 px, its trust frame included, measured by the web
# journey (tests/web/genui.spec.mjs "Slots"), by card (mandate 10.1.4: a slot
# counts toward the 560 px budget like any block, and is never folded).
SLOT_HEIGHTS = {"trade_approval": 230, "settle": 460}
# What only the fixed cards and their trust frame say (the clients' own strings, both
# languages): an agent's card that says it is refused, so it can never pass for one (10.2.2).
FRAME_MARKS = ("fixed card", "بطاقة ثابتة")
FIXED_LABELS = (
    "Approval request",
    "طلب موافقة",
    "Trading request",
    "طلب تداول",
    "Approve",
    "موافقة",
    "Reject",
    "رفض",
    "The broker did not confirm this trade",
    "الوسيط لم يؤكد هذه الصفقة",
    "It executed",
    "نُفذت",
    "It did not execute",
    "لم تُنفذ",
    "Unknown: release the hold",
    "غير معروفة — ارفع التعليق",
)


@dataclass
class Evidence:
    name: str
    arguments: dict[str, Any]
    result: Any

    @property
    def record(self) -> dict[str, Any]:
        result: object = self.result
        return cast(dict[str, Any], result) if isinstance(result, dict) else {}


def request_evidence(messages: list[ModelMessage]) -> dict[str, Evidence]:
    """Tool results of the current request (after the owner's latest message), by call id."""
    boundary = max(
        (
            i
            for i, m in enumerate(messages)
            if m.role == "user" and m.context_origin == "conversation"
        ),
        default=-1,
    )
    current = messages[boundary + 1 :]
    calls = {call.id: call for m in current if m.role == "assistant" for call in m.tool_calls}
    evidence: dict[str, Evidence] = {}
    for message in current:
        identity = message.tool_call_id
        if message.role != "tool" or identity is None or identity not in calls:
            continue
        try:
            raw = json.loads(message.content)
        except (ValueError, TypeError):
            continue
        call = calls[identity]
        evidence[identity] = Evidence(call.name, dict(call.arguments), raw)
    return evidence


# Lifecycle states of a journaled operation (lonora_contracts.trading.OperationStatus).
OPERATION_STATUSES = frozenset(
    {"reserved", "submitted", "confirmed", "failed", "ambiguous", "resolved"}
)


def failed(data: Any) -> bool:
    if not isinstance(data, dict):
        return False
    data = cast(dict[str, Any], data)
    return (
        data.get("ok") is False
        or bool(data.get("error"))
        or str(data.get("status", "")).lower() in FAILED
    )


def unconfirmed(data: Any) -> bool:
    """A journaled operation the broker has not confirmed: an object naming an
    ``operation_id`` whose own status (or its ``result``'s, as in a journal excerpt) is not
    ``confirmed``. An agent can never draw such an operation as done (10.3, 6.10)."""
    if not isinstance(data, dict) or "operation_id" not in data:
        return False
    data = cast(dict[str, Any], data)
    status = data.get("status")
    nested = data.get("result")
    if status is None and isinstance(nested, dict):
        status = cast(dict[str, Any], nested).get("status")
    return str(status).lower() != "confirmed"


def holds_unconfirmed(data: Any, depth: int = 0) -> bool:
    """Whether a result names, anywhere within it, an operation the broker has not
    confirmed."""
    if depth > 6:
        return False
    if unconfirmed(data):
        return True
    if isinstance(data, dict):
        return any(holds_unconfirmed(v, depth + 1) for v in cast(dict[str, Any], data).values())
    if isinstance(data, list):
        return any(holds_unconfirmed(v, depth + 1) for v in cast(list[Any], data))
    return False


def unusable(data: Any) -> bool:
    """Not usable as card evidence: a failed result or an unconfirmed operation."""
    return failed(data) or unconfirmed(data)


def _refuse(data: Any) -> None:
    if unconfirmed(data):
        raise ValueError("genui_fact_unconfirmed")
    if failed(data):
        raise ValueError("genui_fact_failed")


def _scalar(value: Any) -> Any:
    """A finite scalar; decimal strings (pydantic's JSON Decimal) become numbers."""
    if isinstance(value, str):
        if DECIMAL.match(value.strip()):
            number = float(value)
            return int(number) if number.is_integer() and "." not in value else number
        return value[:200]
    if isinstance(value, bool) or value is None:
        return value
    if isinstance(value, int | float):
        if not math.isfinite(value):
            raise ValueError("genui_fact_not_finite")
        return value
    raise ValueError("genui_fact_not_scalar")


def _bounded(value: Any, depth: int, count: list[int]) -> Any:
    if isinstance(value, dict):
        if depth >= 3:
            raise ValueError("genui_fact_too_deep")
        result: dict[str, Any] = {}
        for key, item in cast(dict[str, Any], value).items():
            if PRIVATE_KEY.search(key):
                raise ValueError("genui_fact_private")
            _refuse(item)
            result[key] = _bounded(item, depth + 1, count)
        return result
    if isinstance(value, list):
        if depth >= 3:
            raise ValueError("genui_fact_too_deep")
        for item in cast(list[Any], value):
            _refuse(item)
        return [_bounded(item, depth + 1, count) for item in cast(list[Any], value)]
    count[0] += 1
    if count[0] > MAX_OBJECT_SCALARS:
        raise ValueError("genui_fact_too_large")
    return _scalar(value)


def resolve_pointer(data: Any, path: str) -> tuple[Any, str | None]:
    """A scalar, a ``*`` column of at most 100 scalars, or a bounded object."""
    observed: str | None = None
    tokens = [t.replace("~1", "/").replace("~0", "~") for t in path.split("/")[1:]]
    if tokens.count("*") > 1:
        raise ValueError("genui_fact_path_invalid")
    for index, token in enumerate(tokens):
        _refuse(data)
        if isinstance(data, dict):
            data = cast(dict[str, Any], data)
            for key in ("observed_at", "timestamp", "updated_at", "as_of"):
                if isinstance(data.get(key), str):
                    observed = str(data[key])[:80]
                    break
        if PRIVATE_KEY.search(token):
            raise ValueError("genui_fact_private")
        if token == "*":
            if not isinstance(data, list) or len(cast(list[Any], data)) > MAX_COLUMN:
                raise ValueError("genui_fact_column_invalid")
            rest = "/" + "/".join(tokens[index + 1 :]) if index + 1 < len(tokens) else ""
            column = [
                resolve_pointer(item, rest)[0] if rest else _scalar(item)
                for item in cast(list[Any], data)
            ]
            if any(isinstance(item, dict | list) for item in column):
                raise ValueError("genui_fact_column_invalid")
            return column, observed
        if isinstance(data, dict) and token in data:
            data = cast(dict[str, Any], data)[token]
        elif isinstance(data, list) and token.isdigit() and int(token) < len(cast(list[Any], data)):
            data = cast(list[Any], data)[int(token)]
        elif isinstance(data, list) and token == "length":
            for item in cast(list[Any], data):
                _refuse(item)
            data = len(cast(list[Any], data))
        else:
            raise ValueError("genui_fact_path_unknown")
    _refuse(data)
    if isinstance(data, dict | list):
        return _bounded(data, 0, [0]), observed
    return _scalar(data), observed


NUMBER = re.compile(r"\d[\d,]*(?:\.\d+)?")
FACT_TOOLS = re.compile(r"^(?:market_|account_|list_accounts$|trade_record_history$)")


# Arabic-Indic and Persian digits, «٫» and «٬», read as the client reads them.
DIGITS = str.maketrans("٠١٢٣٤٥٦٧٨٩۰۱۲۳۴۵۶۷۸۹٫٬", "01234567890123456789.,")
# The quote and account fields whose values are market or account numbers (rule 2); ids,
# logins, timestamps, digits and volume steps never are (review: no year false positive).
PRICE_KEYS = frozenset(
    {
        "bid",
        "ask",
        "last",
        "mid",
        "price",
        "open",
        "high",
        "low",
        "close",
        "current_price",
        "open_price",
        "price_open",
        "price_current",
        "balance",
        "equity",
        "margin",
        "free_margin",
        "profit",
        "value",
        "stop_loss",
        "take_profit",
        "sl",
        "tp",
        "level",
        "atr",
        "support",
        "resistance",
        "pivot",
    }
)
# Any other price-like field a market or account tool returns (review round 4): reference,
# entry, target and average prices, swing highs and lows, levels.
PRICE_KEY = re.compile(r"(?:^|_)(?:price|swing_high|swing_low|level|stop|target|entry)(?:$|_)")


def _numbers(value: Any) -> set[Decimal]:
    found: set[Decimal] = set()
    if isinstance(value, bool) or value is None:
        return found
    if isinstance(value, int | float):
        if math.isfinite(value):
            found.add(Decimal(str(value)).normalize())
    elif isinstance(value, str):
        for token in NUMBER.findall(value.translate(DIGITS)):
            try:
                found.add(Decimal(token.replace(",", "")).normalize())
            except InvalidOperation:
                continue
    elif isinstance(value, list):
        for item in cast(list[Any], value):
            found |= _numbers(item)
    elif isinstance(value, dict):
        for item in cast(dict[str, Any], value).values():
            found |= _numbers(item)
    return found


# A trade result's own numbers, beside its prices: tickets and volumes.
TRADE_KEYS = frozenset({"broker_id", "position_id", "order_id", "deal_id", "ticket", "volume"})


def _read_values(value: Any, extra: frozenset[str] = frozenset()) -> set[Decimal]:
    """Price-like values only: the PRICE_KEYS fields of a quote or account result (and
    ``extra`` fields, for a trade result)."""
    found: set[Decimal] = set()
    if isinstance(value, dict):
        for key, item in cast(dict[str, Any], value).items():
            listed = key in PRICE_KEYS or key in extra or PRICE_KEY.search(key)
            if listed and not isinstance(item, dict | list):
                found |= _numbers(item)
            else:
                found |= _read_values(item, extra)
    elif isinstance(value, list):
        for item in cast(list[Any], value):
            found |= _read_values(item, extra)
    return found


def _significant(number: Decimal) -> bool:
    return (number != number.to_integral_value() and abs(number) >= 1) or abs(number) >= 1000


def typed_fact_numbers(
    head: dict[str, Any],
    blocks: list[dict[str, Any]],
    state: dict[str, Any],
    calc: dict[str, Any],
    evidence: dict[str, Evidence],
    owner: str,
) -> list[str]:
    """Market or account values read this turn that the card types instead of citing
    through @Fact (rule 2), wherever it types them: text, template braces, calc literals
    and expressions (@Pick constants included), options (values, labels, ``also``) and
    action data, in any digits. Numbers the owner typed are theirs to show."""
    read: set[Decimal] = set()
    for item in evidence.values():
        if FACT_TOOLS.match(item.name) and not failed(item.result):
            read |= {n for n in _read_values(item.result) if _significant(n)}
        elif item.name.startswith("trade_") and not failed(item.result):
            # A trade's ticket, volume and prices are cited, never typed: typed, they
            # could state an operation the broker has not confirmed as done (10.3).
            read |= {n for n in _read_values(item.result, TRADE_KEYS) if _significant(n)}
    said = _numbers(owner)
    shown = {key: value for key, value in head.items() if key not in {"facts", "v"}}
    literals: list[Any] = [shown, state, calc, blocks]
    return sorted(str(n) for n in _numbers(literals) if n in read and n not in said)


def _call_account(item: Evidence, bound_account: str | None) -> str | None:
    account = item.arguments.get("account_id")
    if isinstance(account, str) and account:
        return account
    if bound_account and (item.name.startswith("market_") or item.name.startswith("account_")):
        return bound_account
    return None


def _trim(text: str, cap: int) -> str:
    if len(text) <= cap:
        return text
    cut = text[: cap - 1]
    space = cut.rfind(" ")
    return (cut[:space] if space > cap // 2 else cut).rstrip() + "…"


@dataclass
class AgentScope:
    """The card's agent as the compiler needs it."""

    agent_id: str = ""
    bound_account: str | None = None
    bound_symbol: str | None = None
    # More than one enabled account: an alert's bubble must name its account (docs/genui.md §7), so
    # an account without a verified broker label is listed here as unnamed.
    several_accounts: bool = False
    # The accounts this request read that the server can name (owner-checked, read
    # directly, never from a bounded list).
    named_accounts: frozenset[str] = frozenset()
    # ``(card, record id)`` of the records this card's slots name that exist, belong to
    # this owner and sit in this conversation (``lonora_db.genui_slots``).
    slot_records: frozenset[tuple[str, str]] = frozenset()


# Look-alike letters read as the letter they imitate: Cyrillic and Greek for Latin
# ("Аpprove"), Persian yeh and keheh for Arabic.
CONFUSABLES = str.maketrans(
    "аАвВеЕкКмМнНоОрРсСтТуУхХіІјЈѕЅԁαΑβΒεΕηΗιΙκΚμΜνΝοΟρΡτΤυΥχΧیک",
    "aAbBeEkKmMhHoOpPcCtTyYxXiIjJsSdaAbBeEnHiIkKmMvNoOpPtTuYxXيك",
)


def _plain(text: str) -> str:
    """The comparable form: compatibility forms unified, invisible format characters (zero
    width joiners and spaces, direction marks) removed, look-alike letters read as Latin, then
    folded before punctuation becomes space, so Arabic diacritics never split a word."""
    text = unicodedata.normalize("NFKC", text)
    text = "".join(ch for ch in text if unicodedata.category(ch) != "Cf")
    return " ".join(re.sub(r"[^\w\s]", " ", fold(text.translate(CONFUSABLES))).split())


FIXED_PLAIN = frozenset(_plain(label) for label in FIXED_LABELS)
MARKS_PLAIN = tuple(_plain(mark) for mark in FRAME_MARKS)
# The frame's own icon: an agent's node never wears it.
FRAME_ICON = "shield"
LITERAL = re.compile(r"'([^']*)'")


def shows_frame_mark(text: str) -> bool:
    """Text that says what only the trust frame says."""
    plain = f" {_plain(text)} "
    return any(f" {mark} " in plain for mark in MARKS_PLAIN)


# What separates a fixed card's title from what follows it («طلب موافقة · XAUUSD»).
SEGMENTS = re.compile(r"\s*[·•:|/\u2013\u2014-]\s*")


def imitates_fixed_card(text: str, *, control: bool = False) -> bool:
    """A label an agent's node shows that says what only a fixed card or its trust frame says.
    A heading is refused when it, or one of its separated segments, is a fixed card's words
    («طلب موافقة · XAUUSD»), never for a sentence that starts with them («يستأذن قبل كل صفقة»).
    A Button's label is refused when it even starts with them («Approve trade»): a control is
    what a fixed card's buttons are."""
    if shows_frame_mark(text):
        return True
    plain = _plain(text)
    if control:
        return any(plain == label or plain.startswith(label + " ") for label in FIXED_PLAIN)
    return plain in FIXED_PLAIN or any(
        _plain(part) in FIXED_PLAIN for part in SEGMENTS.split(text) if part.strip()
    )


# Props whose text heads or labels something, the way a fixed card's title and buttons do.
LABEL_PROPS = ("label", "title", "show")
LABEL_TEXT_NODES = frozenset({"Badge", "Title"})
BODY_PROPS = ("text", "hint", "sub", "value", "suffix", "prefix")


def imitation(
    head: dict[str, Any],
    blocks: list[dict[str, Any]],
    envs: list[Any],
    why: str | None,
    fallback: str | None,
) -> bool:
    """Whether the agent's own card looks like a fixed card (mandate 10.2.2): the frame's icon,
    a heading or control label a fixed card shows, or the frame's words anywhere shown. Each
    template is read as written, at each sampled state and by every quoted literal in it."""
    if head.get("icon") == FRAME_ICON:
        return True
    labels: list[str] = [str(head.get("title") or ""), str(head.get("sub") or "")]
    controls: list[str] = []
    body: list[str] = [why or "", fallback or ""]
    for _path, node in walk(blocks):
        if node.get("icon") == FRAME_ICON:
            return True
        for name in LABEL_PROPS:
            if isinstance(node.get(name), str):
                (controls if node["type"] == "Button" else labels).append(node[name])
        for name in BODY_PROPS:
            if isinstance(node.get(name), str):
                (labels if node["type"] in LABEL_TEXT_NODES else body).append(node[name])
        for option in cast(list[Any], node.get("options", [])):
            shown = cast(dict[str, Any], option).get("label") if isinstance(option, dict) else None
            shown = (
                (cast(dict[str, Any], option).get("value") if shown is None else shown)
                if isinstance(option, dict)
                else option
            )
            if shown is not None:
                labels.append(show(shown))
        for row in node.get("rows", []):
            body.extend(cell for cell in row if isinstance(cell, str))

    def readings(text: str) -> list[str]:
        found = [text, *LITERAL.findall(text)]
        found.extend(render_template(text, env) for env in envs)
        return found

    return (
        any(imitates_fixed_card(t) for text in labels for t in readings(text))
        or any(imitates_fixed_card(t, control=True) for text in controls for t in readings(text))
        or any(shows_frame_mark(t) for text in body for t in readings(text))
    )


def _data_keys(action: dict[str, Any], state: dict[str, Any], calc: dict[str, Any]) -> set[str]:
    """State keys a send's data reads, directly or through calc (a literal reads nothing)."""
    keys: set[str] = set()
    data = cast(dict[str, Any], action.get("data", {}))
    pending: list[str] = [v for v in data.values() if isinstance(v, str) and v.startswith("$")]
    seen: set[str] = set()
    while pending:
        read, _functions, _names, _facts = references(pending.pop())
        for key in read:
            if key in state:
                keys.add(key)
            elif key in calc and key not in seen and isinstance(calc[key], str):
                seen.add(key)
                pending.append(calc[key])
    return keys


def owner_words(messages: list[ModelMessage]) -> str:
    """The owner's latest typed message; a card's send is card words, never the owner's
    (its projection starts ``[owner_via_card``, docs/genui.md)."""
    return next(
        (
            m.content
            for m in reversed(messages)
            if m.role == "user"
            and m.context_origin == "conversation"
            and not m.content.startswith("[owner_via_card")
        ),
        "",
    )


def _owner_urls(messages: list[ModelMessage], evidence: dict[str, Evidence]) -> set[str]:
    owner = owner_words(messages)
    urls = set(re.findall(r"https://[^\s<>\"'«»]+", owner))

    def collect(value: Any) -> None:
        if isinstance(value, dict):
            for key, item in cast(dict[str, Any], value).items():
                if key in {"link", "url"} and isinstance(item, str) and item.startswith("https://"):
                    urls.add(item)
                else:
                    collect(item)
        elif isinstance(value, list):
            for item in cast(list[Any], value):
                collect(item)

    for item in evidence.values():
        collect(item.result)
    return urls


def estimate_height(blocks: list[dict[str, Any]], visible: list[bool]) -> int:
    height = 48 + 30 + 22  # header, footer, body padding
    shown = [block for block, on in zip(blocks, visible, strict=True) if on]
    for block in shown:
        height += _node_height(block)
    return height + 14 * max(len(shown) - 1, 0)


def _node_height(node: dict[str, Any]) -> int:
    kind = node["type"]
    if kind == "KeyValue":
        return 37 * len(node["rows"])
    if kind == "Text":
        return 20 * max(1, min(3, math.ceil(len(str(node.get("text", ""))) / 48)))
    if kind == SLOT:
        return SLOT_HEIGHTS[node["card"]]
    if kind == "Row":
        return max((_node_height(child) for child in node["children"]), default=0)
    if kind in {"Col", "Card", "Grid"}:
        children = [_node_height(child) for child in node["children"]]
        if kind == "Grid":
            cols = node.get("cols", 2)
            rows = [max(children[i : i + cols]) for i in range(0, len(children), cols)]
            return sum(rows) + 8 * max(len(rows) - 1, 0)
        return sum(children) + 12 * max(len(children) - 1, 0) + (32 if kind == "Card" else 0)
    return HEIGHTS.get(kind, 40)


def compile_card(
    card: ParsedCard,
    messages: list[ModelMessage],
    scope: AgentScope,
    capabilities: UiCapabilities,
    public_ids: set[str],
    *,
    final: bool,
) -> dict[str, Any]:
    """The stored v2 document. Raises ``CardError`` when the card must fall back."""
    if card.head is None:
        raise CardError("card_fallback")
    diagnostics = card.diagnostics
    head = dict(card.head)
    data = card.data
    state: dict[str, Any] = dict(data.get("state", {}))
    calc: dict[str, Any] = dict(data.get("calc", {}))
    evidence = request_evidence(messages)
    if any(
        item.name in FINANCIAL_CALLS and holds_unconfirmed(item.result)
        for item in evidence.values()
    ):
        # An order or close of this request the broker has not confirmed: the reply is text
        # only, so no card, cited or not, can read as done (10.3, 6.4).
        raise CardError("card_fallback_unconfirmed")

    # Facts, and the card's one account (the first account-bearing fact, as written).
    facts: dict[str, dict[str, Any]] = {}
    account: str | None = None
    for key, reference in cast(dict[str, dict[str, str]], data.get("facts", {})).items():
        item = evidence.get(reference["call"])
        if item is not None and unconfirmed(item.result):
            # No part of a card may present an operation the broker has not confirmed.
            raise CardError("card_fallback_unconfirmed")
        if item is None or failed(item.result):
            facts[key] = {"value": None, "source": item.name if item else "unknown"}
            continue
        call_account = _call_account(item, scope.bound_account)
        if call_account is not None:
            if account is None:
                account = call_account
            elif call_account != account:
                raise CardError("card_fallback_account")
        try:
            value, observed = resolve_pointer(item.result, reference["path"])
        except ValueError as error:
            if str(error) == "genui_fact_unconfirmed":
                raise CardError("card_fallback_unconfirmed") from None
            value, observed = None, None
        except RecursionError:
            value, observed = None, None
        if isinstance(value, str):
            value = redact_private_reply(value, public_ids=public_ids)
        if observed is not None:
            # Source metadata is shown too (the why panel's time): filtered like values.
            observed = redact_private_reply(observed, public_ids=public_ids)
        facts[key] = {
            "value": value,
            "source": item.name[:80],
            "observed_at": observed,
            "account_id": call_account,
        }
    if facts and all(fact["value"] is None for fact in facts.values()):
        raise CardError("card_fallback")
    if scope.bound_account and account is not None and account != scope.bound_account:
        # A fixed-market agent's card is about its own account only (review).
        diagnostics.add("option_out_of_scope", None, "head")
        raise CardError("card_fallback")
    if head.get("mode") == "observed" and not facts:
        # No fact declared: the card shows no market or account number, so it is never
        # labelled observed (mode_checked).
        head.pop("mode")
        diagnostics.add("mode_checked", None, "head")
    elif head.get("mode") == "observed" and not any(f["value"] is not None for f in facts.values()):
        raise CardError("card_fallback")
    currency: str | None = None
    if account is not None:
        for item in evidence.values():
            if (
                item.name not in {"account_read", "account_performance_series"}
                or _call_account(item, scope.bound_account) != account
            ):
                continue
            # ``account_read`` nests the account under ``account`` (review E1).
            nested: Any = item.record.get("account")
            found: Any = (
                cast(dict[str, Any], nested).get("currency") if isinstance(nested, dict) else None
            )
            found = found if isinstance(found, str) else item.record.get("currency")
            if isinstance(found, str):
                currency = found
                break
        if head.get("currency") not in {None, currency}:
            diagnostics.add("prop_dropped", None, "head", "currency")
        head.pop("currency", None)
        if currency and re.fullmatch(r"[A-Z]{3}", currency):
            head["currency"] = currency

    # Symbols verified this turn on the card's account.
    verified: set[str] = set()
    for item in evidence.values():
        if unusable(item.result) or not isinstance(item.result, dict):
            continue
        if account is not None and _call_account(item, scope.bound_account) != account:
            continue
        result = item.record
        if item.name in SYMBOL_TOOLS and isinstance(result.get("symbol"), str):
            verified.add(result["symbol"])
        if item.name == "market_symbols" and isinstance(result.get("symbols"), list):
            verified |= {s for s in cast(list[Any], result["symbols"]) if isinstance(s, str)}

    watch_ids: set[str] = set()
    for item in evidence.values():
        if item.name.startswith("watch_") and not unusable(item.result):
            if isinstance(item.record.get("id"), str):
                watch_ids.add(item.record["id"])
            for watch in cast(list[Any], item.record.get("watches") or []):
                entry = cast(dict[str, Any], watch) if isinstance(watch, dict) else {}
                if isinstance(entry.get("id"), str):
                    watch_ids.add(entry["id"])
    blocks: list[dict[str, Any]] = []
    for index, block in enumerate(card.blocks):
        if block["type"] == SLOT:
            # A slot shows a real record of this owner and conversation, of its own kind,
            # once (mandate 10.2.1); anything else is refused and the card falls back.
            if (block["card"], block["record"]) not in scope.slot_records:
                diagnostics.add("slot_refused", index, SLOT)
                raise CardError("card_fallback_slot")
            if any(b["type"] == SLOT and b["record"] == block["record"] for b in blocks):
                diagnostics.add("block_dropped", index, SLOT)
                continue
        blocks.append(dict(block))
    sends: list[dict[str, Any]] = []
    urls = _owner_urls(messages, evidence) if final else set[str]()

    def check_actions(nodes: list[dict[str, Any]]) -> list[dict[str, Any]]:
        kept: list[dict[str, Any]] = []
        for index, node in enumerate(nodes):
            node = dict(node)
            if "children" in node:
                node["children"] = check_actions(node["children"])
                if not node["children"]:
                    diagnostics.add("block_dropped", index, node["type"])
                    continue
            action = node.get("action")
            if node["type"] == "Button" and action is not None:
                refused = False
                kind = action["do"]
                if kind == "send":
                    intent = action["intent"]
                    registry = REGISTRY.get(intent)
                    allowed: set[str] = (
                        {f.name for f in registry.fields if not f.server_set}
                        if registry
                        else set[str]()
                    )
                    if (
                        intent_denied(intent)
                        or intent not in capabilities.intents
                        or registry is None
                        or set(action.get("data", {})) - allowed
                        or (registry.name == "ask" and action.get("data"))
                    ):
                        refused = True
                    else:
                        types = {f.name: f.type for f in registry.fields}
                        for name, value in cast(dict[str, Any], action.get("data", {})).items():
                            if isinstance(value, str) and value.startswith("$"):
                                # A state key or a calc name, evaluated by the server.
                                refused |= value[1:] not in state | calc
                            elif types.get(name) == "watch":
                                # A watch id is a literal from this turn's evidence.
                                refused |= value not in watch_ids
                            elif types.get(name) in {"instrument", "account"}:
                                refused = True
                        if not refused:
                            lock = action.get("lock", registry.lock)
                            node["action"] = {**action, "lock": bool(lock and registry.lock)}
                            sends.append(node)
                elif kind == "go":
                    refused = action["route"] not in capabilities.routes
                elif kind == "open":
                    refused = final and action["url"] not in urls
                elif kind in {"set", "toggle"}:
                    refused = action["key"] not in state
                if refused:
                    diagnostics.add("action_refused", index, "Button")
                    if node.get("style") == "primary" and kind == "send":
                        raise CardError("card_fallback")
                    continue
            kept.append(node)
        return kept

    blocks = check_actions(blocks)

    # Identity options: the symbol a send's instrument field reads.
    instrument_keys: set[str] = set()
    for node in sends:
        registry = REGISTRY[node["action"]["intent"]]
        for field_spec in registry.fields:
            if field_spec.type == "instrument":
                value = node["action"].get("data", {}).get(field_spec.name)
                if isinstance(value, str) and value.startswith("$"):
                    instrument_keys.add(value[1:])
                elif field_spec.required:
                    raise CardError("card_fallback_reachable")
    alert_card = any(node["action"]["intent"] == "alert.create" for node in sends)
    if instrument_keys and account is None and final:
        raise CardError("card_fallback_account")
    if alert_card and scope.several_accounts and account not in scope.named_accounts:
        raise CardError("card_fallback_account_unnamed")
    for path, node in walk(blocks):
        if node["type"] not in {"Segmented", "Select"} or node.get("bind") not in instrument_keys:
            continue
        options: list[Any] = []
        for option in cast(list[Any], node["options"]):
            entry = cast(dict[str, Any], option) if isinstance(option, dict) else {"value": option}
            value = entry.get("value")
            label = entry.get("label", value)
            if not isinstance(value, str) or value not in verified:
                diagnostics.add("option_unverified", None, node["type"], path)
                continue
            if alert_card and scope.bound_symbol and value != scope.bound_symbol:
                diagnostics.add("option_out_of_scope", None, node["type"], path)
                continue
            if fold(str(label)) not in {fold(name) for name in known_names(str(value))}:
                diagnostics.add("identity_label_mismatch", None, node["type"], path)
                raise CardError("card_fallback_reachable")
            options.append(option)
        initial = state.get(node["bind"])
        values = [
            cast(dict[str, Any], o).get("value") if isinstance(o, dict) else o for o in options
        ]
        if not options or (initial is not None and initial not in values):
            raise CardError("card_fallback_reachable")
        node["options"] = options
    if final:
        for key in instrument_keys:
            if (
                not any(
                    n.get("bind") == key and n["type"] in {"Segmented", "Select"}
                    for _p, n in walk(blocks)
                )
                and state.get(key) not in verified
            ):
                raise CardError("card_fallback_reachable")

    # A dropped input that a send reads, or that was required, leaves a half-built form.
    read_keys: set[str] = set()
    for node in sends:
        read_keys |= _data_keys(node["action"], state, calc)
    if read_keys & card.dropped_binds:
        raise CardError("card_fallback_reachable")
    if final and card.dropped * 2 > card.dropped + len(card.blocks):
        raise CardError("card_fallback")

    # Text caps (the full text stays in the fallback).
    head["title"] = _trim(head["title"], TEXT_CAPS["title"])
    if "sub" in head:
        head["sub"] = _trim(head["sub"], TEXT_CAPS["sub"])
    for _path, node in walk(blocks):
        if isinstance(node.get("label"), str) and "{" not in node["label"]:
            cap = TEXT_CAPS["button"] if node["type"] == "Button" else TEXT_CAPS["label"]
            node["label"] = _trim(node["label"], cap)

    # The read-only delivery row, directly above the block holding the alert.create send.
    if alert_card:
        for index, block in enumerate(blocks):
            holds = any(
                n["type"] == "Button" and n.get("action", {}).get("intent") == "alert.create"
                for _p, n in walk([block])
            )
            if holds:
                blocks.insert(index, {"type": "Delivery", "channels": list(capabilities.delivery)})
                break

    # Rule 2: a market or account value read this turn is shown only through @Fact.
    owner = owner_words(messages)
    if typed_fact_numbers(head, blocks, state, calc, evidence, owner):
        raise CardError("card_fallback_typed_fact")

    # Privacy over every display string as the client renders it (review S2): templated
    # head text and plain-string option labels included, at the initial state and at each
    # state an option selects (its value and its ``also``).
    fact_values = {k: f["value"] for k, f in facts.items()}
    env = environment(state, calc, fact_values)

    def rendered(at: Any) -> list[str]:
        out = [render_template(head["title"], at), render_template(head.get("sub") or "", at)]
        for _path, node in walk(blocks):
            for name in DISPLAYED:
                if isinstance(node.get(name), str):
                    out.append(render_template(node[name], at))
            for option in cast(list[Any], node.get("options", [])):
                if isinstance(option, dict):
                    # The client shows ``label ?? value`` as a template (UiCard optionList).
                    item = cast(dict[str, Any], option)
                    shown = item.get("label")
                    shown = item.get("value") if shown is None else shown
                    if shown is not None:
                        out.append(render_template(show(shown), at))
                elif option is not None:
                    out.append(show(option))  # a plain option is shown raw
            for row in node.get("rows", []):
                out.extend(render_template(c, at) for c in row if isinstance(c, str))
            copied = copy_text(node)
            if copied is not None:
                out.append(render_template(copied, at))
        return out

    def raw() -> list[str]:
        """Every displayed string as written (and the calc sources they read), so a branch
        no sampled state renders is still read; action data is never shown, so not read."""
        found: list[str] = [str(head.get("title") or ""), str(head.get("sub") or "")]
        found.extend(str(v) for v in calc.values() if isinstance(v, str))
        for _path, node in walk(blocks):
            for name in DISPLAYED:
                if isinstance(node.get(name), str):
                    found.append(node[name])
            for option in cast(list[Any], node.get("options", [])):
                if isinstance(option, dict):
                    item = cast(dict[str, Any], option)
                    found.extend(
                        show(item[k]) for k in ("label", "value") if item.get(k) is not None
                    )
                elif option is not None:
                    found.append(show(option))
            for row in node.get("rows", []):
                found.extend(c for c in row if isinstance(c, str))
            copied = copy_text(node)
            if copied is not None:
                found.append(copied)
        return found

    states: list[dict[str, Any]] = [state]
    for _path, node in walk(blocks):
        bind = node.get("bind")
        for option in cast(list[Any], node.get("options", [])):
            if not isinstance(bind, str) or not isinstance(option, dict):
                continue
            item = cast(dict[str, Any], option)
            also: Any = item.get("also")
            extra = cast(dict[str, Any], also) if isinstance(also, dict) else {}
            states.append({**state, bind: item.get("value"), **extra})
    strings: list[str] = []
    envs = [environment(at, calc, fact_values) for at in states[:24]]
    for at_env in envs:
        strings.extend(rendered(at_env))
    strings.extend(raw())
    strings.extend(str(v) for v in state.values() if isinstance(v, str))
    for text in strings:
        if public_reply_violation(text, public_ids=public_ids):
            raise CardError("card_fallback_private")
        if UNBOUND.search(text):
            # A placeholder the card computes but never fills is never shown (review).
            raise CardError("card_fallback_binding")
    if imitation(head, blocks, envs, card.why, card.fallback):
        # Only a slot shows a fixed card; the agent's own nodes never look like one.
        raise CardError("card_fallback_imitation")
    if not final:
        from .public_stream import EFFECT_CLAIM

        if any(EFFECT_CLAIM.search(text) for text in strings):
            raise CardError("card_effect_claim")

    # Budget: at most 6 visible top-level blocks and 560 px at rest; never fold the send,
    # required inputs, inputs the send reads or the delivery row; above 720 px, fall back.
    def visible_now(items: list[dict[str, Any]]) -> list[bool]:
        return [bool(evaluate(b.get("when", True), env, False)) for b in items]

    def protected(block: dict[str, Any]) -> bool:
        for _p, n in walk([block]):
            if n["type"] in {"Delivery", SLOT} or (
                n["type"] == "Button" and n.get("action", {}).get("do") == "send"
            ):
                return True
            if n.get("required") or n.get("bind") in read_keys:
                return True
        return False

    def holds_send(block: dict[str, Any]) -> bool:
        return any(
            n["type"] == "Delivery"
            or (n["type"] == "Button" and n.get("action", {}).get("do") == "send")
            for _p, n in walk([block])
        )

    if final:
        shown = visible_now(blocks)
        if sum(shown) > 6 or estimate_height(blocks, shown) > RESTING_LIMIT:
            folded: list[dict[str, Any]] = []
            kept_blocks = list(blocks)
            while kept_blocks:
                shown = visible_now(kept_blocks)
                if (
                    sum(shown) + (1 if folded else 0) <= 6
                    and estimate_height(kept_blocks, shown) + (40 if folded else 0) <= RESTING_LIMIT
                ):
                    break
                candidates = [
                    i for i, b in enumerate(kept_blocks) if not protected(b) and b["type"] != "More"
                ]
                if not candidates:
                    break
                folded.insert(0, kept_blocks.pop(candidates[-1]))
            if folded:
                # The fold sits right above the delivery row and the send, which stay last.
                tail = len(kept_blocks)
                while tail and holds_send(kept_blocks[tail - 1]):
                    tail -= 1
                kept_blocks.insert(tail, {"type": "More", "children": folded})
                diagnostics.add("budget_folded")
            blocks = kept_blocks
        if estimate_height(blocks, visible_now(blocks)) > HARD_LIMIT:
            raise CardError("card_fallback_budget")

    why = card.why
    if final and not why:
        why = DEFAULT_WHY.get(head["kind"], DEFAULT_WHY["form"])
        diagnostics.add("why_default")
    fallback = card.fallback
    if not fallback:
        # A partial card carries the fallback of what is built so far, so a turn that
        # stops or fails mid-build always has text to stand in for it (review E2).
        fallback = generated_fallback(head, blocks, env)
        if final:
            diagnostics.add("fallback_generated")
    document: dict[str, Any] = {
        **head,
        "facts": facts,
        "state": state,
        "calc": calc,
        "blocks": blocks,
        "fallback": redact_private_reply(fallback or "", public_ids=public_ids),
    }
    if why:
        document["why"] = redact_private_reply(why, public_ids=public_ids)
    if account is not None:
        document["account_id"] = account
    if scope.agent_id:
        document["agent_id"] = scope.agent_id
    return UiDocument.model_validate(document).model_dump(mode="json", exclude_none=True)


def generated_fallback(head: dict[str, Any], blocks: list[dict[str, Any]], env: Any) -> str:
    """Headings, text, KeyValue rows, Stats and inputs as Markdown."""
    lines = [f"**{head['title']}**"]
    for _path, node in walk(blocks):
        if node["type"] in {"Text", "Note", "Title", "Markdown", "Badge"}:
            lines.append(render_template(node["text"], env))
        elif node["type"] == "Stat":
            lines.append(
                f"- **{render_template(node['label'], env)}:** {render_template(node['value'], env)}"
            )
        elif node["type"] == "KeyValue":
            lines.extend(
                f"- **{render_template(str(k), env)}:** {render_template(str(v), env)}"
                for k, v in node["rows"]
            )
        elif node["type"] in INPUTS:
            value = env.values.get(node["bind"])
            lines.append(f"- {node['label']}: {'' if value is None else value}")
    return "\n".join(line for line in lines if line)[:1500]


def diagnostics_codes(diagnostics: Diagnostics) -> list[dict[str, Any]]:
    return diagnostics.items[:24]
