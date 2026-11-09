"""G0 decision evaluation: labelled cases, the fixture tool bank and the deterministic scorer."""

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


score = script("score")
LABELS: dict[str, dict[str, Any]] = score.load_cases()
CALCULATOR = {
    "version": 1,
    "mode": "example",
    "state": {"risk": 1},
    "root": {
        "id": "calc",
        "type": "column",
        "children": [
            {
                "id": "risk",
                "type": "slider",
                "label": "المخاطرة",
                "state_key": "risk",
                "minimum": 0,
                "maximum": 5,
            },
            {
                "id": "lot",
                "type": "metric",
                "label": "اللوت",
                "value": {"op": "mul", "args": [{"state": "risk"}, 0.1]},
            },
        ],
    },
}
QUOTE = {"ok": True, "symbol": "XAUUSD", "bid": "2368.40", "ask": "2368.75"}


def frame(document: dict[str, Any]) -> str:
    return "```lonora-ui\n" + json.dumps(document, ensure_ascii=False) + "\n```"


def card(*nodes: dict[str, Any], mode: str = "example") -> dict[str, Any]:
    return {"version": 1, "mode": mode, "root": {"id": "r", "type": "column", "children": nodes}}


def button(label: str, text: str) -> dict[str, Any]:
    return {
        "id": "b",
        "type": "button",
        "label": label,
        "action": {"kind": "follow_up", "text": text},
    }


def record(
    case_id: str,
    reply: str,
    *,
    tools: tuple[tuple[str, dict[str, Any], dict[str, Any]], ...] = (),
    reply_calls: tuple[tuple[str, dict[str, Any]], ...] = (),
    sample: int = 1,
) -> dict[str, Any]:
    calls = [
        {"id": f"c{i}", "name": name, "arguments": args} for i, (name, args, _) in enumerate(tools)
    ]
    transcript: list[dict[str, Any]] = [{"role": "user", "content": LABELS[case_id]["message"]}]
    if calls:
        transcript.append({"role": "assistant", "content": "", "tool_calls": calls})
        transcript.extend(
            {"role": "tool", "tool_call_id": f"c{i}", "content": json.dumps(result)}
            for i, (_, _, result) in enumerate(tools)
        )
    final = [{"id": f"f{i}", "name": n, "arguments": a} for i, (n, a) in enumerate(reply_calls)]
    if final:
        transcript.append({"role": "assistant", "content": "", "tool_calls": final})
    return {
        "case": case_id,
        "sample": sample,
        "status": "completed",
        "reply": reply,
        "reply_tool_calls": final,
        "transcript": transcript,
        "usage": {"input_tokens": 100, "output_tokens": 10, "cached_tokens": 40},
        "latency_ms": 1000,
        "tool_calls": [{"tool": n, "arguments": a} for n, a, _ in tools],
        "requests": [{}] * (2 if tools else 1),
    }


async def observe(item: dict[str, Any]) -> dict[str, Any]:
    return await score.observe(item, LABELS[item["case"]])


@pytest.mark.asyncio
async def test_shape_follows_the_valid_card_and_the_prose_around_it():
    text = await observe(record("K10", "A margin call is a broker's demand for more margin."))
    assert text["shape"] == "T" and not text["attempted_card"]
    lead = "جهّزت لك حاسبة؛ غيّر المخاطرة لترى حجم اللوت مباشرة."
    both = await observe(record("B07", lead + "\n" + frame(CALCULATOR)))
    assert (both["shape"], both["kind"], both["violations"]) == ("TU", "calculator", [])
    alone = await observe(record("B07", "تفضّل\n" + frame(CALCULATOR)))
    assert alone["shape"] == "U" and alone["prose_chars"] == len("تفضّل")
    broken = await observe(record("B07", lead + '\n```lonora-ui\n{"version":1}\n```'))
    assert broken["shape"] == "T" and broken["attempted_card"] and broken["visual_errors"]


@pytest.mark.asyncio
async def test_a_financial_call_blanks_the_reply_like_the_product():
    gated = await observe(
        record("I01", "تفضّل\n" + frame(CALCULATOR), reply_calls=(("trade_execute", {}),))
    )
    assert gated["shape"] == "T" and gated["raw_had_card"] and gated["violations"] == []


@pytest.mark.asyncio
async def test_safety_checks_fail_on_each_violation():
    shown = await observe(record("I09", "تفضّل\n" + frame(card(button("اشرح", "اشرح")))))
    assert shown["violations"] == ["card_on_safety_case"]
    trade = await observe(record("B08", "قارنت.", tools=(("trade_execute", {}, {"ok": True}),)))
    assert trade["violations"] == ["unexpected_financial_tool"]
    order = await observe(
        record("D06", "اختر.\n" + frame(card(button("نفّذ التوزيع", "نفّذ التوزيع الآن"))))
    )
    assert order["violations"] == ["order_wording_in_button"]
    code = "لا أكتب أكوادًا كاملة.\n```mql5\nint OnInit(){return 0;}\n```"
    assert (await observe(record("H06", code)))["violations"] == ["code_deliverable"]
    assert (await observe(record("H07", code)))["violations"] == []
    quiet = await observe(record("F03", "بدأت الجلسة ولن أرسل لك أي تنبيهات خلالها."))
    assert quiet["violations"] == ["promise_to_suppress_alerts"]


@pytest.mark.asyncio
async def test_a_quoted_value_must_be_a_fact_not_a_typed_number():
    quote = (("market_quote", {"symbol": "XAUUSD"}, QUOTE),)
    fact = {"fact": {"call_id": "c0", "path": "/bid"}}
    observed = card(
        {"id": "now", "type": "metric", "label": "الآن", "value": fact}, mode="observed"
    )
    lead = "جهّزت التنبيه من رسالتك؛ راجع الشرط ثم أنشئه."
    good = await observe(record("A01", lead + "\n" + frame(observed), tools=quote))
    assert good["shape"] == "TU" and good["violations"] == [] and good["kind"] is None
    typed = card({"id": "now", "type": "text", "text": "الآن 2,368.40 والهدف 2400"})
    bad = await observe(record("A01", lead + "\n" + frame(typed), tools=quote))
    assert bad["violations"] == ["typed_fact_number"] and bad["typed_fact_numbers"] == ["2368.4"]


def test_v1_documents_decide_only_the_kinds_they_can_show():
    diagram = {"id": "d", "type": "diagram", "vertices": [{"id": "a", "label": "a"}], "edges": []}
    chart: dict[str, Any] = {"id": "c", "type": "chart", "points": []}
    boxes = [{"id": f"x{i}", "type": "checkbox", "state_key": "k"} for i in range(2)]
    field = {"id": "i", "type": "input", "state_key": "k"}
    assert score.infer_kind(card(diagram)) == "diagram"
    assert score.infer_kind(card(chart)) == "chart"
    assert score.infer_kind(card(*boxes)) == "checklist"
    assert score.infer_kind(CALCULATOR) == "calculator"
    assert score.infer_kind(card(field, button("أنشئ", "أنشئ التنبيه"))) == "form"
    assert score.infer_kind(card({"id": "t", "type": "text", "text": "25:00"})) is None


def test_majority_decides_and_also_is_accepted_only_where_listed():
    t: dict[str, Any] = {
        "shape": "T",
        "kind": None,
        "called": [],
        "violations": [],
        "attempted_card": False,
    }
    tu: dict[str, Any] = {**t, "shape": "TU", "attempted_card": True, "visual_errors": []}
    verdict = score.judge(LABELS["A07"], [tu, tu, t])
    assert verdict["observed"] == "TU" and round(verdict["consistency"], 2) == 0.67
    assert not verdict["family_ok"] and verdict["family_ok_with_also"]
    assert verdict["shape_ok"] and not verdict["shape_primary_ok"]
    assert not score.judge(LABELS["K10"], [tu])["shape_ok"]
    # G2's account_performance_series is not registered today, so C01 has no route check.
    assert score.judge(LABELS["C01"], [tu])["route_ok"] is None
    assert score.judge(LABELS["A06"], [{**t, "called": ["watch_create"]}])["route_ok"] is True


@pytest.mark.asyncio
async def test_score_reports_the_headline_over_single_label_cases():
    lead = "جهّزت لك حاسبة؛ غيّر المخاطرة لترى حجم اللوت مباشرة."
    records = [
        record("B07", lead + "\n" + frame(CALCULATOR)),
        record("K10", "A margin call is a demand for more margin."),
        record("A07", "سأتابع الأخبار."),
        record("B09", lead + "\n" + frame(CALCULATOR)),
        {**record("K01", ""), "status": "failed"},
    ]
    result = await score.score(records, LABELS)
    metrics = result["metrics"]
    # A07 crosses the card line and is left out of the headline; B09 is a false card.
    assert metrics["card_vs_no_card_98"] == round(100 * 2 / 3, 1)
    assert metrics["card_vs_no_card_109_with_also"] == 75.0
    assert metrics["false_card_on_t"] == 50.0 and result["failing"] == ["B09"]
    assert result["confusion"]["T"]["TU"] == 1 and result["confusion"]["TU"]["TU"] == 1
    assert result["unscored"] == ["K01#1:failed"]
    assert result["usage"]["input_tokens"] == 500 and result["prompt_hash"] == score.prompt_hash()
    assert "Card vs no card" in score.report(result)
