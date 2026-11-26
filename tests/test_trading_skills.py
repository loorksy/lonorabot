"""The trading knowledge library (docs/proposals/trading-expertise.md 1.1, 2.4).

Eighteen built-in skills teach a professional trader's judgment, never conditions (VISION
5.1, 5.2, P1). Each parses, fits its size target, carries an English trigger and its topic
in Arabic, names only what Lonora's tool registry defines, and holds no rule language. A
number appears only in a passage marked "Illustration". Writers can check one skill with
``pytest tests/test_trading_skills.py -k <id>``.
"""

import re
from functools import cache
from html import escape
from typing import Any, cast

import pytest
from lonora_agent.context.skills import CATALOG_CHARS, catalog_lines
from lonora_agent.skills.registry import SkillDefinition, SkillRegistry, built_in_skills
from lonora_agent.skills.resolver import (
    ACTIVE_BUDGET,
    SCOPE_RISK_CLASSES,
    SkillSignals,
    eligibility_reason,
    resolve_skills,
)
from lonora_tools.loader import load_tools

TRADING_SKILLS = (
    "market-structure",
    "multi-timeframe",
    "sessions-and-time",
    "chart-patterns",
    "candles-and-breakouts",
    "indicators-as-context",
    "news-and-macro",
    "trade-planning",
    "risk-and-sizing",
    "exits-and-management",
    "trade-review",
    "method-intake",
    "family-forex",
    "family-metals",
    "family-indices",
    "family-energy",
    "pre-trade-check",
    "trader-psychology",
)
FAMILY_SKILLS = ("family-forex", "family-metals", "family-indices", "family-energy")
BODY_CHARS = 5000
DESCRIPTION_CHARS = 200
# The fixed schema per topic (1.1.4). "When to use" is the description; the reasoning
# itself sits under the skill's own topic headings.
SCHEMA_HEADINGS = (
    ("What you are deciding",),
    ("What to check",),
    ("Weak when",),
    ("How to say it", "Saying it"),
)

ARABIC = re.compile(r"[؀-ۿ]")
LATIN = re.compile(r"[A-Za-z]")
SNAKE = re.compile(r"\b[a-z][a-z0-9]*(?:_[a-z0-9]+)+\b")
# Ordinary MetaTrader symbol shapes (EURUSD, XAUUSD.pro, US30, NAS100, USOIL, GOLD), not
# file names such as MEMORY.md; the agent finds the broker's own names with market_symbols
# (Amendment 2, 1.1.6).
SYMBOL = re.compile(
    r"\b[A-Z]{6}\b(?!\.md)"
    r"|\b(?:US|UK|GER|DE|JP|JPN|HK|AUS|FRA|EU|ESP|NAS|SPX|NDX|DJ|USTEC)\d{2,4}\b"
    r"|\b(?:USOIL|UKOIL|NGAS|XNG|XTI|XBR|GOLD|DXY|USDX)\b"
)
# A digit or a spelled count next to a unit (2.4), a fraction of the size, a ratio such as
# 1:2, a threshold word before a number, or a comparison operator: allowed only in a
# passage marked "Illustration".
NUMBER = re.compile(
    r"(?<![\w.,])\d(?:[\d.,]*\d)?\s*-?\s*(?:%|percent\b|R\b|x\b|×|ATRs?\b|pips?\b|points?\b|lots?\b"
    r"|min(?:ute)?s?\b|h(?:ou)?rs?\b|days?\b|bars?\b|candles?\b|periods?\b|trades?\b"
    r"|loss(?:es)?\b|positions?\b|entry\b|entries\b|standard deviations?\b|sigma\b)"
    r"|\b(?:two|three|four|five|six|seven|eight|nine|ten)\s+(?:percent\b|R\b|ATRs?\b|pips?\b"
    r"|points?\b|lots?\b|min(?:ute)?s?\b|h(?:ou)?rs?\b|days?\b|weeks?\b|bars?\b|candles?\b"
    r"|sessions?\b|trades?\b|loss(?:es)?\b|wins?\b|positions?\b|entries\b)"
    r"|\b(?:half|a third|a quarter)\s+(?:size|the size|off|comes off"
    r"|of (?:the|your|his|my) (?:size|position|volume|risk))\b"
    r"|\b1\s*:\s*\d"
    r"|\b(?:above|below|over|under|beyond|exceeds?|exceeding|greater than|less than"
    r"|more than|fewer than|at least|at most|no more than|minimum(?: of)?|maximum(?: of)?)"
    r"\s+[-+]?\d"
    r"|\s[<>]=?\s|[≤≥]",
    re.IGNORECASE,
)
# Conditions, caps and gates (P1, 5.1, 5.2). "must" and "never" stay for honesty
# ("never call a wick a break"), never for a trading choice.
RULE = re.compile(
    r"\bmust(?: not|n't)? (?:trade|enter|buy|sell|open|add|risk|take|hold|close|exit|wait|skip)\b"
    r"|\b(?:never|do not|don't) (?:trade|enter|buy|sell|open a|add to|risk more|take a trade"
    r"|take trades)\b"
    r"|\bonly (?:trade|enter|buy|sell|take|open|add|risk)\w*\b"
    r"|\b(?:trade|enter|buy|sell)\w* only (?:when|if|after|on|during|with|in)\b"
    r"|\bminimum (?:of )?(?:r:r|rr\b|r/r|reward|risk[- ]?reward|reward[- ]to[- ]risk"
    r"|risk[- ]to[- ]reward)"
    r"|\b(?:r:r|rr|r/r|reward[- ]to[- ]risk|risk[- ]reward)(?: ratio)? (?:of )?(?:at least|above"
    r"|over|no less than|>)"
    r"|\b(?:no more than|at most|maximum(?: of)?|max\.?|up to|limit(?:ed)? to|cap(?:ped)? at) \S+"
    r" (?:open |simultaneous |concurrent |new )?(?:trades|positions|entries|orders)\b"
    r"|\b(?:stop|halt|pause|cease|quit) trading (?:after|if|when|for|until)\b"
    r"|\bat least \S+ (?:confluences?|confirmations?|factors|signals|conditions|timeframes)\b"
    r"|\b(?:required|mandatory|necessary) (?:before|to) (?:trade|trading|enter|entering)\b"
    r"|\bkill switch\b|\bcircuit breaker\b",
    re.IGNORECASE,
)
PASSAGE_START = re.compile(r"\s*(?:#|[-*]\s|\d+[.)]\s|Illustration)")
# The MetaTrader terminal's timeframe names; the tools take 15m, 1h, 4h, 1d.
TERMINAL_TIMEFRAME = re.compile(r"\b(?:MN|[MHDW])\d{1,2}\b")


@cache
def skills() -> dict[str, SkillDefinition]:
    return built_in_skills()


@cache
def registry_names() -> frozenset[str]:
    """Tool names plus the argument names and values their schemas define."""
    names: set[str] = set()

    def walk(node: Any) -> None:
        if isinstance(node, dict):
            for key, value in cast(dict[str, Any], node).items():
                if key == "properties" and isinstance(value, dict):
                    names.update(cast(dict[str, Any], value))
                elif key == "enum" and isinstance(value, list):
                    names.update(item for item in cast(list[Any], value) if isinstance(item, str))
                walk(value)
        elif isinstance(node, list):
            for item in cast(list[Any], node):
                walk(item)

    for definition in load_tools().definitions():
        names.add(definition.name)
        walk(definition.parameters)
    return frozenset(names)


def passages(text: str) -> list[str]:
    """Paragraphs, list items, headings and Illustration lines, each joined to one line."""
    result: list[list[str]] = []
    for line in text.splitlines():
        if not line.strip():
            result.append([])
        elif PASSAGE_START.match(line) or not result:
            result.append([line])
        else:
            result[-1].append(line)
    return [" ".join(" ".join(lines).split()) for lines in result if lines]


def unmarked_numbers(text: str) -> list[str]:
    return [
        passage
        for passage in passages(text)
        if "Illustration" not in passage and NUMBER.search(passage)
    ]


def rule_language(text: str) -> list[str]:
    return [match.group(0) for match in RULE.finditer(" ".join(text.split()))]


def test_the_library_is_the_owner_approved_eighteen() -> None:
    # 17 of section 1.2 without family-crypto-cfd (TX-D2), plus pre-trade-check and
    # trader-psychology (the owner's gold-agent specification).
    assert len(set(TRADING_SKILLS)) == 18
    assert set(TRADING_SKILLS) <= skills().keys()
    assert not any("crypto" in identity for identity in skills())


@pytest.mark.parametrize("identity", TRADING_SKILLS)
def test_manifest_is_read_only_knowledge_loaded_on_request(identity: str) -> None:
    manifest = skills()[identity].manifest
    assert manifest.source == "builtin" and manifest.stability == "stable"
    assert manifest.activation.mode == "explicit" and manifest.activation.triggers == []
    # Knowledge never grants authority and needs no tool, so it is eligible everywhere.
    assert manifest.risk_class == "read_only"
    assert manifest.required_tools == [] and manifest.required_capabilities == []
    # A dependency would pull its body into every view of this skill.
    assert manifest.dependencies == [] and manifest.conflicts == []
    assert manifest.priority == 50 and manifest.context_budget == 6000
    tools = load_tools()
    for scope in SCOPE_RISK_CLASSES:
        signals = SkillSignals(scope=scope, available_tools=frozenset(tools.names(scope)))
        assert eligibility_reason(skills()[identity], signals, {}) is None, scope


@pytest.mark.parametrize("identity", TRADING_SKILLS)
def test_description_is_a_trigger_naming_the_topic_in_english_and_arabic(identity: str) -> None:
    description = skills()[identity].manifest.description
    assert description.startswith("Use when "), description
    assert LATIN.search(description) and ARABIC.search(description), description
    assert len(description) <= DESCRIPTION_CHARS, len(description)
    assert not rule_language(description)


@pytest.mark.parametrize("identity", TRADING_SKILLS)
def test_body_fits_its_size_target_in_english_with_the_schema(identity: str) -> None:
    body = skills()[identity].content
    assert len(body) <= BODY_CHARS, len(body)
    assert not ARABIC.search(body), "the body is English; replies follow the owner's language"
    headings = [line[3:].strip() for line in body.splitlines() if line.startswith("## ")]
    for names in SCHEMA_HEADINGS:
        assert any(heading.startswith(names) for heading in headings), names
    # At least one topic heading carries the reasoning itself.
    assert len(headings) > len(SCHEMA_HEADINGS), headings


@pytest.mark.parametrize("identity", TRADING_SKILLS)
def test_body_names_only_registry_tools_and_no_broker_symbol(identity: str) -> None:
    body = skills()[identity].content
    # Snake case is reserved for tool names and their argument names and values; write
    # fields and concepts in plain words. Planned tools (trade_lessons_find) do not exist yet.
    unknown = sorted(set(SNAKE.findall(body)) - registry_names())
    assert not unknown, unknown
    assert not SYMBOL.findall(body), SYMBOL.findall(body)


@pytest.mark.parametrize("identity", TRADING_SKILLS)
def test_body_writes_timeframes_as_the_tools_take_them(identity: str) -> None:
    # market_snapshot and market_candles refuse M15 or H1 (unsupported_timeframe), so an
    # example the model copies must already be a valid argument.
    body = skills()[identity].content
    assert not TERMINAL_TIMEFRAME.findall(body), TERMINAL_TIMEFRAME.findall(body)


@pytest.mark.parametrize("identity", TRADING_SKILLS)
def test_body_has_no_rule_language_and_numbers_only_as_illustrations(identity: str) -> None:
    body = skills()[identity].content
    assert not rule_language(body), rule_language(body)
    assert not unmarked_numbers(body), unmarked_numbers(body)


@pytest.mark.parametrize("identity", FAMILY_SKILLS)
def test_family_skill_starts_from_the_contract_specification(identity: str) -> None:
    # Families are recognised from the contract, never from a symbol list (1.1.6).
    body = skills()[identity].content
    assert "contract specification" in body.lower()
    assert "market_instrument" in body


def test_the_guards_catch_rules_and_keep_honest_wording() -> None:
    for rule in (
        "You must not trade if the spread is wide.",
        "Use a minimum R:R before entering.",
        "Take a maximum N trades per day.",
        "Only trade when price is near support.",
        "Stop trading after two losses in a row.",
        "Wait for at least three confluences.",
    ):
        assert rule_language(rule), rule
    for number in (
        "Risk 1% per trade.",
        "Aim for 2R or more.",
        "Place the stop 1.5 ATR away.",
        "Keep a 1:3 reward to risk.",
        "Wait 30 minutes after the release.",
        "RSI above 70 is a sell.",
        "Trade when fast > slow.",
        "Wait two hours after the release.",
        "Hold half size into the data.",
        "Take a third off at the first target.",
    ):
        assert unmarked_numbers(number), number
    honest = (
        "- A break is a candle close beyond the level; never call a wick a break.\n"
        "Never carry points or pips from one symbol to another.\n"
        "Illustration: a stop 1.5 ATR away is noise on one symbol\n"
        "and 2 days of range on another.\n"
        "1. Closed bars; name a forming bar as forming on the 4h candles and 15m bars.\n"
        "- Two shapes overlap in the favourable half of the range.\n"
        'Never "it may go up or down". Not trading is a decision.'
    )
    assert not rule_language(honest)
    assert not unmarked_numbers(honest)


def test_the_trade_bundle_and_any_four_trading_skills_fit_one_run() -> None:
    # TX-D4: structure, planning, risk and the instrument's family read together with the
    # trade procedures. Checked against the four largest bodies.
    largest = sorted(TRADING_SKILLS, key=lambda identity: -len(skills()[identity].content))[:4]
    requested = frozenset({"trade-management", *largest})
    tools = load_tools()
    selection = resolve_skills(
        SkillRegistry(list(skills().values())),
        SkillSignals(trigger="", requested=requested, available_tools=frozenset(tools.names())),
        ACTIVE_BUDGET,
    )
    assert requested <= {item.manifest.id for item in selection.selected}, selection.rejected


def test_every_built_in_skill_fits_the_catalog_and_overflow_is_counted() -> None:
    lines = [
        "- " + escape(identity) + " — " + escape(definition.manifest.description)
        for identity, definition in sorted(skills().items())
    ]
    assert catalog_lines(lines) == "\n".join(lines)
    assert len("\n".join(lines)) <= CATALOG_CHARS
    # Owner skills past the room are cut at whole lines and counted, never cut mid-line.
    assert catalog_lines(["- a — one", "- b — two", "- c — three"], 20) == (
        "- a — one\n- b — two\n1 more: use skills_list"
    )
    assert catalog_lines(["- a — one"], 3) == "1 more: use skills_list"
    assert catalog_lines([]) == ""
