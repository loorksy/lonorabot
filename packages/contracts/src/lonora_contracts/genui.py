"""lonora-ui v2 documents (GENUI_PLAN §2.2, §7.1, §9.1).

The model writes one card per reply inside the ``lonora-ui`` fence, one JSON object per
line: a head line (``{"v":2,…}``), an optional data line (facts, state, calc), one line per
top-level block and a closing line (``why``, ``fallback``). This module parses and repairs
those lines structurally (no evidence, no database): an invalid optional prop is dropped
(``prop_dropped``), a block with an unknown type or a missing required prop is dropped
(``block_dropped``), an unknown icon is omitted (``icon_unknown``). Evidence, options, the
card's account, the delivery row and the budget are the compiler's
(``lonora_agent.genui_compile``).

Node props are checked by a table rather than one pydantic model per node, so a bad
optional prop can be dropped without losing the block (the repair rules of §9.4). The
stored, compiled document is re-validated by ``UiDocument`` on every write.
"""

from __future__ import annotations

import json
import math
import re
from collections.abc import Callable, Iterator
from dataclasses import dataclass, field
from typing import Any, Literal, cast

from pydantic import Field, model_validator

from .domain import Contract
from .genui_expr import ExpressionError, parse, references, template_expressions
from .genui_functions import KNOWN
from .genui_icons import ICON_NAMES, canonical_icon

MAX_LINE_BYTES = 6000
MAX_BLOCK_LINES = 12
MAX_VISIBLE_BLOCKS = 6
MAX_STATE_KEYS = 24
MAX_CALC = 24
MAX_FACTS = 24
MAX_CHILDREN = 8
MAX_DEPTH = 4
KEY = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,31}$")
# A client route name (``chat-prefs``); the compile step checks it against the routes.
ROUTE = re.compile(r"^[a-z][a-z0-9-]{0,31}$")
BLOCKED_KEYS = frozenset({"__proto__", "prototype", "constructor"})
KINDS = (
    "calculator",
    "form",
    "picker",
    "chart",
    "choice",
    "checklist",
    "quiz",
    "timer",
    "diagram",
    "receipt",
)
Kind = Literal[
    "calculator",
    "form",
    "picker",
    "chart",
    "choice",
    "checklist",
    "quiz",
    "timer",
    "diagram",
    "receipt",
]
TONES = ("info", "good", "warn", "bad", "muted", "accent")
CHANNELS = ("app", "push", "call")
TEXT_CAPS = {"title": 32, "sub": 48, "label": 24, "option": 16, "button": 24}


@dataclass
class Diagnostics:
    """Structural codes only (code, block index, node type, path), never model text."""

    items: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())

    def add(self, code: str, block: int | None = None, node: str | None = None, path: str = ""):
        entry: dict[str, Any] = {"code": code}
        if block is not None:
            entry["block"] = block
        if node is not None and re.fullmatch(r"[A-Za-z]{1,16}", node):
            entry["node"] = node
        if path and re.fullmatch(r"[a-z_.0-9]{1,48}", path):
            entry["path"] = path
        self.items.append(entry)

    def codes(self) -> list[str]:
        return [item["code"] for item in self.items]


class CardError(ValueError):
    """The whole card renders its fallback; the code is structural."""


# --- props --------------------------------------------------------------------------------

Check = Callable[[Any], bool]


def _key(value: Any) -> bool:
    return isinstance(value, str) and bool(KEY.match(value)) and value not in BLOCKED_KEYS


def _scalar(value: Any) -> bool:
    return (
        value is None
        or isinstance(value, str | bool)
        or (isinstance(value, int | float) and math.isfinite(value))
    )


def _expr(value: Any) -> bool:
    if isinstance(value, bool) or _scalar(value) and not isinstance(value, str):
        return True
    if not isinstance(value, str):
        return False
    try:
        parse(value)
        _state, functions, _names, _facts = references(value)
    except ExpressionError:
        return False
    return functions <= KNOWN and "Random" not in functions


def _template(value: Any, cap: int) -> bool:
    if not isinstance(value, str) or len(value) > max(cap * 3, cap + 200):
        return False
    if value.count("{") != value.count("}"):
        return False
    return all(_expr(source) for source in template_expressions(value))


def _text(cap: int) -> Check:
    def check(value: Any) -> bool:
        return _template(value, cap)

    return check


def _enum(*choices: object) -> Check:
    def check(value: Any) -> bool:
        return value in choices

    return check


def _bool(value: Any) -> bool:
    return isinstance(value, bool)


def _number(value: Any) -> bool:
    return isinstance(value, int | float) and not isinstance(value, bool) and math.isfinite(value)


def _icon(value: Any) -> bool:
    return canonical_icon(value) is not None


def _short(cap: int) -> Check:
    def check(value: Any) -> bool:
        return isinstance(value, str) and 0 < len(value) <= cap

    return check


Spec = dict[str, tuple[bool, Check | None]]

TEXT_TONE: Check = _enum(*TONES)


def _options(value: Any) -> bool:
    if not isinstance(value, list) or not 1 <= len(cast(list[Any], value)) <= 20:
        return False
    for item in cast(list[Any], value):
        if isinstance(item, dict):
            item = cast(dict[str, Any], item)
            if set(item) - {"value", "label", "also"} or not _scalar(item.get("value")):
                return False
            if "label" in item and not _template(item["label"], TEXT_CAPS["option"]):
                return False
            also = item.get("also")
            if also is not None and (
                not isinstance(also, dict)
                or len(cast(dict[str, Any], also)) > 8
                or not all(_key(k) and _scalar(v) for k, v in cast(dict[str, Any], also).items())
            ):
                return False
        elif not _scalar(item):
            return False
    return True


def _rows(value: Any) -> bool:
    if not isinstance(value, list) or not 1 <= len(cast(list[Any], value)) <= 8:
        return False
    return all(
        isinstance(row, list)
        and len(cast(list[Any], row)) == 2
        and all(
            _template(cell, 60) if isinstance(cell, str) else _scalar(cell)
            for cell in cast(list[Any], row)
        )
        for row in cast(list[Any], value)
    )


ACTIONS = ("set", "toggle", "reset", "copy", "open", "go", "send")


def _data_value(value: Any) -> bool:
    """A send's data field: ``$key`` (a state or calc name) or a literal, never an expression."""
    if isinstance(value, str):
        return _key(value[1:]) if value.startswith("$") else len(value) <= 200
    return _scalar(value)


def _action(value: Any) -> bool:
    if not isinstance(value, dict):
        return False
    value = cast(dict[str, Any], value)
    kind = value.get("do")
    if kind == "send":
        data = value.get("data", {})
        return (
            set(value) <= {"do", "intent", "data", "lock"}
            and isinstance(value.get("intent"), str)
            and len(value["intent"]) <= 48
            and isinstance(data, dict)
            and len(cast(dict[str, Any], data)) <= 12
            and all(_key(k) and _data_value(v) for k, v in cast(dict[str, Any], data).items())
            and isinstance(value.get("lock", True), bool)
        )
    if kind == "go":
        route = value.get("route")
        return set(value) <= {"do", "route"} and isinstance(route, str) and bool(ROUTE.match(route))
    if kind == "set":
        return set(value) <= {"do", "key", "value"} and _key(value.get("key"))
    if kind == "toggle":
        return set(value) <= {"do", "key"} and _key(value.get("key"))
    if kind == "reset":
        return set(value) == {"do"}
    if kind == "copy":
        return set(value) <= {"do", "text"} and _template(value.get("text"), 400)
    if kind == "open":
        url = value.get("url")
        return (
            set(value) <= {"do", "url"}
            and isinstance(url, str)
            and url.startswith("https://")
            and "{" not in url
            and len(url) <= 400
        )
    return False


COMMON: Spec = {"when": (False, _expr)}
NODES: dict[str, Spec] = {
    "Segmented": {
        "bind": (True, _key),
        "label": (True, _text(TEXT_CAPS["label"])),
        "options": (True, _options),
    },
    "Select": {
        "bind": (True, _key),
        "label": (True, _text(TEXT_CAPS["label"])),
        "options": (True, _options),
    },
    "Number": {
        "bind": (True, _key),
        "label": (True, _text(TEXT_CAPS["label"])),
        "hint": (False, _text(60)),
        "prefix": (False, _short(6)),
        "suffix": (False, _short(6)),
        "required": (False, _bool),
    },
    "Slider": {
        "bind": (True, _key),
        "label": (True, _text(TEXT_CAPS["label"])),
        "min": (False, _number),
        "max": (False, _number),
        "step": (False, _number),
        "show": (False, _text(40)),
    },
    "Text": {"text": (True, _text(180)), "tone": (False, TEXT_TONE), "size": (False, _enum("sm"))},
    "Title": {"text": (True, _text(60))},
    "Markdown": {"text": (True, _text(600))},
    "Note": {"text": (True, _text(140)), "tone": (False, TEXT_TONE), "icon": (False, _icon)},
    "Badge": {"text": (True, _text(24)), "tone": (False, TEXT_TONE), "icon": (False, _icon)},
    "KeyValue": {"rows": (True, _rows)},
    "Stat": {
        "label": (True, _text(TEXT_CAPS["label"])),
        "value": (True, _text(40)),
        "sub": (False, _text(40)),
        "trend": (False, _expr),
        "tone": (False, TEXT_TONE),
        "icon": (False, _icon),
    },
    "Button": {
        "label": (True, _text(TEXT_CAPS["button"])),
        "action": (False, _action),
        "style": (False, _enum("primary", "outline")),
        "icon": (False, _icon),
        "full": (False, _bool),
        "disabled": (False, _expr),
    },
    "Divider": {},
    "Row": {"children": (True, None)},
    "Col": {"children": (True, None)},
    "Grid": {"children": (True, None), "cols": (False, _enum(1, 2, 3))},
    "Card": {"children": (True, None), "title": (False, _text(32)), "icon": (False, _icon)},
    "More": {"children": (True, None), "label": (False, _text(24))},
}
CONTAINERS = frozenset({"Row", "Col", "Grid", "Card", "More"})
INPUTS = frozenset({"Segmented", "Select", "Number", "Slider"})
ICON_PROPS = frozenset({"icon"})
# The S-A01 slice renders these on web; the rest of R1's nodes follow in the widening.
SLICE_NODES = frozenset(
    {"Segmented", "Number", "Text", "Note", "Button", "Row", "KeyValue", "More", "Divider"}
)


def repair_node(
    raw: Any, diagnostics: Diagnostics, block: int, depth: int = 0, path: str = ""
) -> dict[str, Any] | None:
    """One node with its invalid optional props dropped, or None (``block_dropped``)."""
    if not isinstance(raw, dict) or not isinstance(cast(dict[str, Any], raw).get("type"), str):
        diagnostics.add("block_dropped", block, path=path)
        return None
    raw = cast(dict[str, Any], raw)
    kind = raw["type"]
    spec = NODES.get(kind)
    if spec is None or depth > MAX_DEPTH:
        diagnostics.add("block_dropped", block, kind if spec else None, path)
        return None
    node: dict[str, Any] = {"type": kind}
    for name, value in raw.items():
        if name == "type":
            continue
        required, check = (spec | COMMON).get(name, (None, None))
        if required is None:
            diagnostics.add("prop_dropped", block, kind, f"{path}{name}".lower()[:48])
            continue
        if name == "children":
            continue
        if name in ICON_PROPS:
            icon = canonical_icon(value)
            if icon is None:
                diagnostics.add("icon_unknown", block, kind)
                continue
            node[name] = icon
            continue
        if check is None or not check(value):
            # A button whose action is invalid is dropped, never turned into a question.
            if required or (kind == "Button" and name == "action"):
                diagnostics.add("block_dropped", block, kind, f"{path}{name}".lower()[:48])
                return None
            diagnostics.add("prop_dropped", block, kind, f"{path}{name}".lower()[:48])
            continue
        node[name] = value
    if "children" in spec:
        children = raw.get("children")
        if not isinstance(children, list) or not children:
            diagnostics.add("block_dropped", block, kind, path + "children")
            return None
        repaired = [
            repair_node(child, diagnostics, block, depth + 1, f"{path}{index}.")
            for index, child in enumerate(cast(list[Any], children)[:MAX_CHILDREN])
        ]
        node["children"] = [child for child in repaired if child is not None]
        if not node["children"]:
            diagnostics.add("block_dropped", block, kind, path + "children")
            return None
    missing = [name for name, (required, _check) in spec.items() if required and name not in node]
    if missing and missing != ["children"]:
        diagnostics.add("block_dropped", block, kind, path + missing[0])
        return None
    return node


def bound_keys(raw: Any) -> set[str]:
    """Every ``bind`` inside a raw (possibly invalid) node."""
    keys: set[str] = set()
    if isinstance(raw, dict):
        raw = cast(dict[str, Any], raw)
        if isinstance(raw.get("bind"), str):
            keys.add(raw["bind"])
        children: Any = raw.get("children")
        for child in cast(list[Any], children) if isinstance(children, list) else []:
            keys |= bound_keys(child)
    return keys


def walk(nodes: list[dict[str, Any]], prefix: str = "") -> Iterator[tuple[str, dict[str, Any]]]:
    """Every node with its dotted path (``3`` or ``3.0``), depth first."""
    for index, node in enumerate(nodes):
        path = f"{prefix}{index}"
        yield path, node
        yield from walk(cast(list[dict[str, Any]], node.get("children", [])), path + ".")


def node_at(blocks: list[dict[str, Any]], path: str) -> dict[str, Any] | None:
    for candidate, node in walk(blocks):
        if candidate == path:
            return node
    return None


# --- lines --------------------------------------------------------------------------------


@dataclass
class ParsedCard:
    """What the lines said, after structural repair."""

    head: dict[str, Any] | None = None
    data: dict[str, Any] = field(default_factory=lambda: dict[str, Any]())
    blocks: list[dict[str, Any]] = field(default_factory=lambda: list[dict[str, Any]]())
    why: str | None = None
    fallback: str | None = None
    closed: bool = False
    dropped: int = 0
    # State keys bound by inputs inside dropped blocks (``card_fallback_reachable``).
    dropped_binds: set[str] = field(default_factory=lambda: set[str]())
    lines: int = 0
    diagnostics: Diagnostics = field(default_factory=Diagnostics)


def is_v2_start(first_line: str) -> bool:
    return re.match(r'^\s*\{\s*"v"\s*:\s*2\s*[,}]', first_line) is not None


def _head(raw: Any, diagnostics: Diagnostics) -> dict[str, Any]:
    if not isinstance(raw, dict) or cast(dict[str, Any], raw).get("v") != 2:
        raise CardError("card_fallback")
    raw = cast(dict[str, Any], raw)
    if raw.get("kind") not in KINDS or not isinstance(raw.get("title"), str):
        raise CardError("card_fallback")
    head: dict[str, Any] = {"v": 2, "kind": raw["kind"], "title": raw["title"][:200]}
    for name in raw:
        if name not in {"v", "kind", "title", "sub", "icon", "mode", "currency"}:
            diagnostics.add("prop_dropped", None, "head", name.lower()[:48])
    if isinstance(raw.get("sub"), str):
        head["sub"] = raw["sub"][:200]
    head["icon"] = canonical_icon(raw.get("icon")) or "sparkle"
    if raw.get("icon") is not None and canonical_icon(raw.get("icon")) is None:
        diagnostics.add("icon_unknown", None, "head")
    if raw.get("mode") in {"observed", "example", "estimate"}:
        head["mode"] = raw["mode"]
    elif "mode" in raw:
        diagnostics.add("prop_dropped", None, "head", "mode")
    currency = raw.get("currency")
    if isinstance(currency, str) and re.fullmatch(r"[A-Z]{3}", currency):
        head["currency"] = currency
    return head


def _data(raw: dict[str, Any], diagnostics: Diagnostics) -> dict[str, Any]:
    if set(raw) - {"facts", "state", "calc"}:
        raise CardError("card_fallback")
    facts = raw.get("facts", {})
    state = raw.get("state", {})
    calc = raw.get("calc", {})
    if not (isinstance(facts, dict) and isinstance(state, dict) and isinstance(calc, dict)):
        raise CardError("card_fallback")
    facts, state, calc = (
        cast(dict[str, Any], facts),
        cast(dict[str, Any], state),
        cast(dict[str, Any], calc),
    )
    if len(facts) > MAX_FACTS or len(state) > MAX_STATE_KEYS or len(calc) > MAX_CALC:
        raise CardError("card_fallback")
    clean_facts: dict[str, dict[str, str]] = {}
    for key, value in facts.items():
        if (
            not _key(key)
            or not isinstance(value, dict)
            or set(cast(dict[str, Any], value)) != {"call", "path"}
            or not isinstance(value["call"], str)
            or not isinstance(value["path"], str)
            or not value["path"].startswith("/")
            or len(value["call"]) > 200
            or len(value["path"]) > 200
        ):
            raise CardError("card_fallback")
        clean_facts[key] = {"call": value["call"], "path": value["path"]}
    clean_state: dict[str, Any] = {}
    for key, value in state.items():
        if not _key(key):
            raise CardError("card_fallback")
        if not _scalar(value) and not (
            isinstance(value, list | dict) and len(json.dumps(value)) <= 2000
        ):
            raise CardError("card_fallback")
        clean_state[key] = value
    clean_calc: dict[str, Any] = {}
    for key, value in calc.items():
        # A calc is an expression or a literal (the reference's uxExpr returns non-strings).
        if not _key(key) or key in clean_state or not _scalar(value) or not _expr(value):
            raise CardError("card_fallback")
        clean_calc[key] = value
    return {"facts": clean_facts, "state": clean_state, "calc": clean_calc}


def parse_lines(raw: str, *, final: bool) -> ParsedCard:
    """Parse the complete lines of a fence body. A partial last line is never read while
    streaming (``final`` false); the head and data lines failing makes the card fall back."""
    card = ParsedCard()
    lines = raw.split("\n")
    if not final:
        lines = lines[:-1]
    for number, line in enumerate(lines):
        line = line.strip()
        if not line:
            continue
        card.lines += 1
        if len(line.encode()) > MAX_LINE_BYTES:
            if card.head is None:
                raise CardError("card_fallback")
            card.dropped += 1
            card.diagnostics.add("block_dropped", len(card.blocks))
            continue
        try:
            value = json.loads(line)
        except (ValueError, RecursionError) as error:
            if card.head is None:
                raise CardError("card_fallback") from error
            card.dropped += 1
            card.diagnostics.add("block_dropped", len(card.blocks))
            continue
        if card.head is None:
            card.head = _head(value, card.diagnostics)
            continue
        if not isinstance(value, dict):
            card.dropped += 1
            card.diagnostics.add("block_dropped", len(card.blocks))
            continue
        value = cast(dict[str, Any], value)
        if card.closed:
            card.diagnostics.add("block_dropped", len(card.blocks))
            continue
        if "why" in value or "fallback" in value:
            if isinstance(value.get("why"), str):
                card.why = value["why"][:220]
            if isinstance(value.get("fallback"), str):
                card.fallback = value["fallback"][:1500]
            card.closed = True
            continue
        if "type" not in value and not card.blocks and number <= 2 and not card.data:
            card.data = _data(value, card.diagnostics)
            continue
        if len(card.blocks) + card.dropped >= MAX_BLOCK_LINES:
            card.diagnostics.add("block_dropped", len(card.blocks))
            continue
        node = repair_node(value, card.diagnostics, len(card.blocks))
        if node is None:
            card.dropped += 1
            card.dropped_binds |= bound_keys(value)
        else:
            card.blocks.append(node)
    if card.head is None and final:
        raise CardError("card_fallback")
    return card


# --- the stored, compiled document --------------------------------------------------------


class UiFact(Contract):
    value: Any = None
    source: str = Field(max_length=80)
    observed_at: str | None = Field(default=None, max_length=80)
    account_id: str | None = Field(default=None, max_length=80)


class UiDocument(Contract):
    """The compiled v2 card as stored in ``rich_content`` (part ``ui``)."""

    v: Literal[2]
    kind: Kind
    title: str = Field(max_length=40)
    sub: str | None = Field(default=None, max_length=60)
    icon: str = "sparkle"
    mode: Literal["observed", "example", "estimate"] | None = None
    currency: str | None = Field(default=None, pattern=r"^[A-Z]{3}$")
    account_id: str | None = Field(default=None, max_length=80)
    agent_id: str | None = Field(default=None, max_length=80)
    facts: dict[str, UiFact] = Field(default_factory=dict)
    state: dict[str, Any] = Field(default_factory=dict)
    calc: dict[str, Any] = Field(default_factory=dict)
    blocks: list[dict[str, Any]] = Field(
        default_factory=lambda: list[dict[str, Any]](), max_length=MAX_BLOCK_LINES + 2
    )
    why: str | None = Field(default=None, max_length=220)
    fallback: str = Field(default="", max_length=1500)

    @model_validator(mode="after")
    def structural(self) -> UiDocument:
        if self.icon not in ICON_NAMES:
            raise ValueError("genui_icon_unknown")
        if len(self.facts) > MAX_FACTS or len(self.state) > MAX_STATE_KEYS:
            raise ValueError("genui_document_too_large")
        diagnostics = Diagnostics()
        for index, block in enumerate(self.blocks):
            if block.get("type") == "Delivery":
                if set(block) != {"type", "channels"} or not all(
                    channel in CHANNELS for channel in block.get("channels", [])
                ):
                    raise ValueError("genui_delivery_invalid")
                continue
            if repair_node(block, diagnostics, index) != block:
                raise ValueError("genui_block_invalid")
        for source in self.calc.values():
            if not _scalar(source) or not _expr(source):
                raise ValueError("genui_expression_invalid")
        return self
