"""Intent registry v1 of generated-UI sends (GENUI_PLAN §8.3): closed and non-financial.

A card's ``send {intent, data, lock}`` asks the card's agent to act with its own tools; it
grants nothing. The server composes the owner's bubble from the intent's template filled
with validated data and the server's own names for identity-typed fields; the model never
writes it. Denied families are refused at compile time and by the API.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal, InvalidOperation
from typing import Any, Literal

from .instrument_names import instrument_name

FieldType = Literal["instrument", "account", "watch", "enum", "price", "text", "int", "bool"]


@dataclass(frozen=True)
class IntentField:
    name: str
    type: FieldType
    required: bool = True
    choices: tuple[str, ...] = ()
    server_set: bool = False


@dataclass(frozen=True)
class Intent:
    name: str
    fields: tuple[IntentField, ...] = ()
    lock: bool = True
    templates: dict[str, str] = field(default_factory=lambda: dict[str, str]())


REGISTRY: dict[str, Intent] = {
    item.name: item
    for item in (
        Intent("ask", lock=False),
        Intent(
            "alert.create",
            (
                IntentField("symbol", "instrument"),
                IntentField("account_id", "account", server_set=True),
                IntentField("dir", "enum", choices=("above", "below")),
                IntentField("price", "price"),
            ),
            templates={
                "ar": "أنشئ تنبيهًا: {symbol:name} {dir:فوق|تحت} {price}",
                "en": "Create an alert: {symbol:name} {dir:above|below} {price}",
            },
        ),
        Intent(
            "alert.off",
            (IntentField("watch_id", "watch"),),
            templates={"ar": "أوقف تنبيه {watch_id:name}", "en": "Stop the alert {watch_id:name}"},
        ),
    )
}
# Listed in the capability block in this order once their tool path exists (§3.6).
S_A01_INTENTS = ("ask", "alert.create", "alert.off")

DENIED = re.compile(
    r"^(?:trade|order|position|close|risk|limit|grant|authority|ladder|trading|restriction"
    r"|credential|model|agent|supervision|profile|settings)(?:[._-]|$)"
    r"|^close|pay|transfer|withdraw|deposit",
    re.I,
)


def intent_denied(name: object) -> bool:
    """A denied family, or anything outside the closed registry."""
    return not isinstance(name, str) or bool(DENIED.search(name)) or name not in REGISTRY


class IntentDataError(ValueError):
    pass


def _price(value: Any) -> float:
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise IntentDataError("ui_submit_data_invalid")
    if not math.isfinite(value) or value <= 0 or value > 1e9:
        raise IntentDataError("ui_submit_data_invalid")
    return float(value)


def validate_data(intent: Intent, data: dict[str, Any]) -> dict[str, Any]:
    """Bounded scalars only, exactly the intent's fields."""
    if set(data) - {item.name for item in intent.fields}:
        raise IntentDataError("ui_submit_data_invalid")
    clean: dict[str, Any] = {}
    for item in intent.fields:
        value = data.get(item.name)
        if value is None:
            if item.required:
                raise IntentDataError("ui_submit_data_invalid")
            continue
        if item.type == "price":
            clean[item.name] = _price(value)
        elif item.type == "enum":
            if value not in item.choices:
                raise IntentDataError("ui_submit_data_invalid")
            clean[item.name] = value
        elif item.type in {"instrument", "account", "watch", "text"}:
            if not isinstance(value, str) or not 0 < len(value) <= 200:
                raise IntentDataError("ui_submit_data_invalid")
            clean[item.name] = value
        elif item.type == "int":
            if isinstance(value, bool) or not isinstance(value, int) or abs(value) > 1e6:
                raise IntentDataError("ui_submit_data_invalid")
            clean[item.name] = value
        elif item.type == "bool":
            if not isinstance(value, bool):
                raise IntentDataError("ui_submit_data_invalid")
            clean[item.name] = value
    return clean


def price_text(value: float, digits: int = 2) -> str:
    """Latin digits with grouping, the instrument's digits (the reference's own style)."""
    try:
        exact = Decimal(repr(value)).quantize(Decimal(1).scaleb(-digits), rounding=ROUND_HALF_UP)
    except InvalidOperation:
        return str(value)
    return f"{exact:,.{digits}f}"


def price_digits(symbol: str) -> int:
    """Two decimals for metals, indices and crypto quoted like gold; four for FX pairs."""
    upper = symbol.upper()
    if upper.startswith("XA") or upper.startswith("US") and upper[2:4].isdigit():
        return 2
    if upper.startswith("BTC"):
        return 2
    if "JPY" in upper:
        return 3
    return 4 if len(upper) >= 6 and upper[:6].isalpha() else 2


Namer = dict[str, str]


def compose_bubble(
    intent: Intent, data: dict[str, Any], language: str, names: Namer | None = None
) -> str:
    """The owner's bubble for a non-``ask`` intent, from its template and validated data.

    ``names`` maps identity field names to the server's own names (watch names, account
    labels); instruments are named from the instrument table.
    """
    language = "en" if language == "en" else "ar"
    template = intent.templates[language]
    names = names or {}

    def fill(match: re.Match[str]) -> str:
        name, _, spec = match.group(1).partition(":")
        value = data.get(name)
        kind = next((item.type for item in intent.fields if item.name == name), None)
        if spec == "name":
            if kind == "instrument":
                return instrument_name(str(value), language)
            return names.get(name, "")
        if spec and "|" in spec and kind == "enum":
            options = next(item.choices for item in intent.fields if item.name == name)
            words = spec.split("|")
            return words[options.index(value)] if value in options else ""
        if kind == "price" and isinstance(value, int | float):
            symbol = str(data.get("symbol", ""))
            return price_text(float(value), price_digits(symbol))
        return "" if value is None else str(value)

    text = re.sub(r"\{([a-z_]+(?::[^}]*)?)\}", fill, template)
    account = names.get("account_id")
    if intent.name == "alert.create" and account:
        text += " · " + account
    return text


# --- watch names, in watchCondition's words (packages/core/src/agent-status.ts:102-134) ---

WATCH_WORDS = {
    "ar": {
        "above": "فوق",
        "below": "تحت",
        "cross_above": "يتجاوز صعودًا",
        "cross_below": "يكسر هبوطًا",
        "changed": "يتغير",
        "closed": "يُغلق",
        "opened": "يُفتح",
        "due": "حدث مستحق",
        "position": "المركز",
        "account": "الحساب",
        "calendar": "المفكرة الاقتصادية",
        "pattern": "نمط",
        "balance": "الرصيد",
        "equity": "حقوق الملكية",
        "margin": "الهامش",
        "free_margin": "الهامش الحر",
        "profit": "الربح",
        "volume": "الحجم",
    },
    "en": {
        "above": "above",
        "below": "below",
        "cross_above": "crosses above",
        "cross_below": "crosses below",
        "changed": "changes",
        "closed": "closes",
        "opened": "opens",
        "due": "event due",
        "position": "Position",
        "account": "Account",
        "calendar": "Economic calendar",
        "pattern": "pattern",
        "balance": "balance",
        "equity": "equity",
        "margin": "margin",
        "free_margin": "free margin",
        "profit": "profit",
        "volume": "volume",
    },
}
METRICS = ("balance", "equity", "margin", "free_margin", "profit", "volume")
DIRECTION_CONTROLS = re.compile("[‪-‮⁦-⁩]")


def isolate(value: str) -> str:
    """The TypeScript ``isolate``: embedded direction controls dropped, then FSI…PDI."""
    return "⁨" + DIRECTION_CONTROLS.sub("", value) + "⁩"


def watch_name(watch: dict[str, Any], language: str) -> str:
    """What one watch waits for, exactly as the status line and the watch list say it."""
    text = WATCH_WORDS["en" if language.startswith("en") else "ar"]
    condition = text.get(watch.get("condition") or "", "") if watch.get("condition") else ""
    level_raw = watch.get("level")
    level = isolate(level_raw) if level_raw is not None and level_raw != "0" else ""
    symbol = isolate(watch["symbol"]) if watch.get("symbol") else ""
    metric = text[watch["metric"]] if watch.get("metric") in METRICS else ""
    kind = watch.get("kind")
    if kind == "calendar":
        return f"{text['calendar']} · {text['due']}"
    if kind == "account":
        parts = [text["account"], metric, condition, level]
    elif kind == "position":
        parts = [text["position"], symbol, metric, condition, level]
    elif kind == "indicator":
        parts = [
            isolate(watch["indicator"].upper()) if watch.get("indicator") else "",
            isolate(watch["timeframe"]) if watch.get("timeframe") else "",
            symbol,
            condition,
            level,
        ]
    elif kind == "dynamic":
        parts = [symbol, text["pattern"]]
    else:
        parts = [symbol, condition, level]
    return " ".join(part for part in parts if part)
