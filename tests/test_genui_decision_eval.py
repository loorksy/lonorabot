"""G0 decision evaluation: the labelled cases and the fixture tool bank."""

import importlib.util
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path
from types import ModuleType
from typing import Any

import pytest
from lonora_core.user_error import LonoraError
from lonora_tools.loader import load_tools

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / "tests/fixtures/genui_decision"


def script(name: str) -> ModuleType:
    path = ROOT / "scripts/genui_eval" / (name + ".py")
    spec = importlib.util.spec_from_file_location("genui_eval_" + name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


bank = script("bank")
CASES: list[dict[str, Any]] = [
    json.loads(line) for line in (FIXTURES / "cases.jsonl").read_text().splitlines()
]
CONTEXTS: dict[str, list[dict[str, str]]] = json.loads((FIXTURES / "contexts.json").read_text())


def test_cases_match_the_plan_counts():
    assert len(CASES) == 109 and len({case["id"] for case in CASES}) == 109
    assert Counter(case["lang"] for case in CASES) == {"ar": 93, "en": 16}
    assert Counter(case["shape"] for case in CASES) == {"T": 60, "TU": 35, "U": 14}
    assert sum(case["follow_up"] for case in CASES) == 20
    assert sum(case["safety"] for case in CASES) == 17
    assert sum(bool(case["also"]) for case in CASES) == 30
    assert sum(case["single_label"] for case in CASES) == 98
    assert sum(case["domain"] in {"trading", "lonora"} for case in CASES) == 93
    crossing = [case["id"] for case in CASES if case["crosses_card_line"]]
    assert crossing == "A07 A12 B08 C04 D06 D07 E05 F06 G02 G04 J09".split()
    assert all(case["shape"] == "T" for case in CASES if case["safety"])
    for case in CASES:
        card = case["shape"] != "T"
        assert case["crosses_card_line"] == any(
            (also["shape"] != "T") != card for also in case["also"]
        )
        assert case["single_label"] == (not case["crosses_card_line"])


def test_every_follow_up_has_its_seeded_turns():
    for case in CASES:
        seed = case["context"].get("seed")
        assert (seed is not None) == case["follow_up"], case["id"]
        if seed:
            turns = CONTEXTS[seed]
            assert turns[-1]["role"] == "assistant" and turns[0]["role"] == "user"
    assert {case["context"].get("seed") for case in CASES} - {None} == set(CONTEXTS)


def test_tool_bank_matches_the_real_tool_contracts():
    """Drift in a tool name, an argument or a returned contract model fails here."""
    registry = load_tools()
    tools: dict[str, Any] = bank.load_bank()["tools"]
    assert set(tools) == set(bank.CONTRACTS)
    assert not set(tools) & bank.PASS_THROUGH
    for name, entry in tools.items():
        tool = registry.tools[name]
        fields = set(tool.input_type.model_fields)
        assert set(entry.get("by", [])) <= fields, name
        if "echo" in entry:
            assert not tool.read_only, name
        results = bank.entry_results(entry)
        assert results, name
        for result in results:
            assert "ok" not in result, name
            for pointer, model in bank.CONTRACTS[name]:
                found = list(bank.parts(result, pointer))
                assert found or "*" in pointer, (name, pointer)
                for value in found:
                    model.model_validate(value)


def test_every_expected_tool_is_answered_or_absent_today():
    registry = load_tools()
    tools = bank.load_bank()["tools"]
    for case in CASES:
        for name in case["tools_expected"]:
            if name in registry.tools:
                assert name in tools or name in bank.PASS_THROUGH, (case["id"], name)
            else:
                # G2 adds this read; today's route check skips it.
                assert name == "account_performance_series", (case["id"], name)


def test_bank_answers_like_the_real_handlers():
    tools = bank.materialize(
        bank.load_bank(),
        {
            "account_id": "acct",
            "lonora_id": "lonora",
            "thread_id": "thread",
            "gold_agent_id": "gold",
            "euro_agent_id": "euro",
            "research_agent_id": "research",
        },
        datetime(2026, 12, 2, 12, 0, tzinfo=UTC),
    )
    quote = bank.answer(tools["market_quote"], {"account_id": "acct", "symbol": "xauusd"})
    assert quote["bid"] == "2368.40" and quote["observed_at"] < "2026-12-02T12:00:00Z"
    with pytest.raises(LonoraError, match="quote_unavailable"):
        bank.answer(tools["market_quote"], {"account_id": "acct", "symbol": "BTCUSD"})
    watch = bank.answer(tools["watch_create"], {"symbol": "EURUSD", "level": "1.08"})
    assert watch["payload"]["symbol"] == "EURUSD" and watch["payload"]["level"] == "1.08"
    assert tools["list_accounts"]["result"]["accounts"][0]["connection_id"] == "acct"
