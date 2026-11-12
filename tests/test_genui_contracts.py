"""lonora-ui v2 contracts: shared vectors, line parsing and repair, intents, names."""

import json
from pathlib import Path
from typing import Any

import pytest
from lonora_contracts.genui import CardError, UiDocument, parse_lines
from lonora_contracts.genui_expr import Env, environment, evaluate, render_template
from lonora_contracts.genui_intents import (
    REGISTRY,
    compose_bubble,
    intent_denied,
    validate_data,
    watch_name,
)
from lonora_contracts.instrument_names import instrument_name, known_names

FIXTURES = Path(__file__).parent / "fixtures" / "genui"
A01 = (FIXTURES / "documents" / "valid" / "a01-alert.lonora-ui").read_text()


def test_shared_expression_vectors() -> None:
    vectors = json.loads((FIXTURES / "expr-vectors.json").read_text())
    for case in vectors["cases"]:
        env = Env(values=vectors["values"], facts=vectors["facts"])
        assert evaluate(case["src"], env) == case["expected"], case["src"]


def test_shared_watch_name_vectors() -> None:
    for case in json.loads((FIXTURES / "watch-name-vectors.json").read_text())["cases"]:
        assert watch_name(case["watch"], case["locale"]) == case["expected"]


def test_a01_parses_without_diagnostics_and_computes_the_screenshot_values() -> None:
    card = parse_lines(A01, final=True)
    assert card.head == {
        "v": 2,
        "kind": "form",
        "title": "تنبيه سعر",
        "sub": "يصلك عند تحقق الشرط",
        "icon": "bell",
        "mode": "observed",
    }
    assert [block["type"] for block in card.blocks] == [
        "Segmented",
        "Segmented",
        "Number",
        "Text",
        "Note",
        "Button",
    ]
    assert card.closed and card.diagnostics.items == []
    env = environment(
        card.data["state"], card.data["calc"], {"xau": 2368.4, "xag": 28.92, "eur": 1.0842}
    )
    assert render_template(card.blocks[2]["hint"], env) == "الآن 2368.40"
    assert render_template(card.blocks[3]["text"], env) == "يبعد **1.33%** عن السعر الحالي"
    assert evaluate("$price&&!$hit", env) is True


def test_streaming_never_reads_a_partial_line() -> None:
    lines = A01.split("\n")
    partial = "\n".join(lines[:3]) + "\n" + lines[3][:40]
    card = parse_lines(partial, final=False)
    assert len(card.blocks) == 1 and not card.closed


def test_repair_drops_props_blocks_and_icons() -> None:
    raw = "\n".join(
        [
            '{"v":2,"kind":"form","title":"t","icon":"no-such-icon"}',
            '{"type":"Text","text":"ok","tone":"purple","onClick":"x"}',
            '{"type":"Frobnicate","text":"x"}',
            '{"type":"Number","label":"no bind"}',
            '{"type":"Note","text":"n","icon":"trend-down"}',
            '{"type":"Text","text":"{@Random(1,2)}"}',
            '{"why":"w","fallback":"f"}',
        ]
    )
    card = parse_lines(raw, final=True)
    assert card.head is not None and card.head["icon"] == "sparkle"
    assert card.blocks == [
        {"type": "Text", "text": "ok"},
        {"type": "Note", "text": "n", "icon": "trendDown"},
    ]
    codes = card.diagnostics.codes()
    assert codes.count("block_dropped") == 3 and codes.count("prop_dropped") == 2
    assert "icon_unknown" in codes


@pytest.mark.parametrize(
    "head",
    ['{"v":1,"kind":"form","title":"t"}', '{"v":2,"kind":"poster","title":"t"}', "not json"],
)
def test_invalid_head_falls_back(head: str) -> None:
    with pytest.raises(CardError):
        parse_lines(head + '\n{"type":"Text","text":"x"}', final=True)


def test_expressions_are_bounded() -> None:
    env = Env(values={})
    assert evaluate("1+" * 300 + "1", env) is None
    assert evaluate("((((((((((((((1))))))))))))))", env) == 1
    assert evaluate("$x.constructor", Env(values={"x": {}})) is None


@pytest.mark.parametrize(
    "name",
    [
        "risk.apply",
        "trade.execute",
        "Trade.Create",
        "order_place",
        "grant.widen",
        "close_all",
        "limit.raise",
        "ladder.up",
        "trading.resume",
        "pay.bill",
        "withdraw",
        "alert.make",
        "model.switch",
        "profile.set",
    ],
)
def test_denied_and_unknown_intents_are_refused(name: str) -> None:
    assert intent_denied(name)


def test_registry_is_non_financial() -> None:
    for name in REGISTRY:
        assert not intent_denied(name)
    assert set(REGISTRY) == {"ask", "alert.create", "alert.off"}


def test_alert_create_bubble_uses_the_server_names() -> None:
    intent = REGISTRY["alert.create"]
    data = validate_data(
        intent, {"symbol": "XAUUSD.r", "account_id": "acc", "dir": "above", "price": 2400}
    )
    assert compose_bubble(intent, data, "ar") == "أنشئ تنبيهًا: الذهب فوق 2,400.00"
    assert compose_bubble(intent, data, "en") == "Create an alert: Gold above 2,400.00"
    assert (
        compose_bubble(intent, data, "ar", {"account_id": "MetaQuotes · 1234"})
        == "أنشئ تنبيهًا: الذهب فوق 2,400.00 · MetaQuotes · 1234"
    )
    euro = validate_data(
        intent, {"symbol": "EURUSD", "account_id": "a", "dir": "below", "price": 1.08}
    )
    assert compose_bubble(intent, euro, "ar") == "أنشئ تنبيهًا: اليورو تحت 1.0800"


@pytest.mark.parametrize(
    "data",
    [
        {"symbol": "XAUUSD", "account_id": "a", "dir": "sideways", "price": 1},
        {"symbol": "XAUUSD", "account_id": "a", "dir": "above", "price": -1},
        {"symbol": "XAUUSD", "account_id": "a", "dir": "above", "price": float("inf")},
        {"symbol": "XAUUSD", "account_id": "a", "dir": "above", "price": True},
        {"symbol": "XAUUSD", "account_id": "a", "dir": "above"},
        {"symbol": "XAUUSD", "account_id": "a", "dir": "above", "price": 1, "text": "buy"},
    ],
)
def test_alert_data_is_bounded(data: dict[str, Any]) -> None:
    with pytest.raises(ValueError):
        validate_data(REGISTRY["alert.create"], data)


def test_alert_off_names_the_watch_in_the_watch_list_words() -> None:
    watch = {"kind": "price", "symbol": "XAUUSD", "condition": "above", "level": "2400"}
    bubble = compose_bubble(
        REGISTRY["alert.off"], {"watch_id": "w1"}, "ar", {"watch_id": watch_name(watch, "ar")}
    )
    assert bubble == "أوقف تنبيه ⁨XAUUSD⁩ فوق ⁨2400⁩"


def test_instrument_names() -> None:
    assert instrument_name("XAUUSD") == "الذهب"
    assert instrument_name("XAUUSDm") == "الذهب"
    assert instrument_name("xauusd") == "الذهب"
    assert instrument_name("NAS100") == "NAS100"
    assert {"الذهب", "ذهب", "XAUUSD", "Gold"} <= known_names("XAUUSD.r")
    assert "الفضة" not in known_names("XAUUSD")


def test_stored_document_revalidates() -> None:
    card = parse_lines(A01, final=True)
    assert card.head is not None
    document = {
        **card.head,
        "facts": {"xau": {"value": 2368.4, "source": "market_quote"}},
        "state": card.data["state"],
        "calc": card.data["calc"],
        "blocks": [*card.blocks, {"type": "Delivery", "channels": ["app"]}],
        "why": card.why,
        "fallback": card.fallback,
    }
    assert UiDocument.model_validate(document).blocks[-1] == {
        "type": "Delivery",
        "channels": ["app"],
    }
    with pytest.raises(ValueError):
        UiDocument.model_validate(
            {**document, "blocks": [{"type": "Delivery", "channels": ["sms"]}]}
        )
    with pytest.raises(ValueError):
        UiDocument.model_validate({**document, "blocks": [{"type": "Html", "html": "<b>"}]})


def test_a_calc_may_be_a_literal_as_in_the_reference() -> None:
    body = A01.replace('"dp":"@Pick($symbol,\'EURUSD\',4,2)"', '"dp":2')
    card = parse_lines(body, final=True)
    assert card.data["calc"]["dp"] == 2
    env = environment(card.data["state"], card.data["calc"], {"xau": 2368.4})
    assert render_template(card.blocks[2]["hint"], env) == "الآن 2368.40"


def test_a_literal_send_value_is_data_and_a_bad_action_drops_its_button() -> None:
    raw = "\n".join(
        [
            '{"v":2,"kind":"receipt","title":"Alert active","icon":"check"}',
            '{"type":"Button","label":"Stop","action":{"do":"send","intent":"alert.off","data":{"watch_id":"47a32ccd-c721-5382-b3b1-9ba4d335db1e"}}}',
            '{"type":"Button","label":"Odd","action":{"do":"launch"}}',
            '{"why":"w","fallback":"f"}',
        ]
    )
    card = parse_lines(raw, final=True)
    assert [b["label"] for b in card.blocks] == ["Stop"]
    assert card.blocks[0]["action"]["data"]["watch_id"].startswith("47a32ccd")


def test_a_malformed_go_route_drops_its_button() -> None:
    raw = "\n".join(
        [
            '{"v":2,"kind":"receipt","title":"Alert active","icon":"check"}',
            '{"type":"Row","children":['
            '{"type":"Button","label":"Plans","action":{"do":"go","route":"schedules"}},'
            '{"type":"Button","label":"Odd","action":{"do":"go","route":"../admin"}},'
            '{"type":"Button","label":"Dash","action":{"do":"go","route":"-x"}}]}',
            '{"why":"w","fallback":"f"}',
        ]
    )
    card = parse_lines(raw, final=True)
    assert [b["label"] for b in card.blocks[0]["children"]] == ["Plans"]
    assert card.blocks[0]["children"][0]["action"] == {"do": "go", "route": "schedules"}


def test_function_arity_is_the_shared_fixture() -> None:
    """Both evaluators refuse a call outside a function's arity (``functions.ts`` ARITY)."""
    from lonora_contracts.genui_functions import ARITY

    shared = json.loads((FIXTURES / "arity.json").read_text())
    assert {name: [low, high] for name, (low, high) in ARITY.items()} == shared


def test_a_calc_chain_of_nested_lists_stays_within_one_budget() -> None:
    """Review round 4: lists of lists built through ``$`` reads are charged as a whole, so
    the chain fails at its first oversized step instead of expanding to gigabytes."""
    import time

    from lonora_contracts.genui_expr import environment, render_template

    calc = {
        "a": "@Join(@Range(0,200),'xxxxxxx')",
        "b": "[" + ",".join(["$a"] * 120) + "]",
        "c": "[" + ",".join(["$b"] * 120) + "]",
    }
    started = time.monotonic()
    env = environment({}, calc, {})
    assert len(env.values["a"]) == 1893
    assert env.values["b"] is None and env.values["c"] == [None] * 120
    assert render_template("{$b}", env) == ""
    assert render_template("{$c}", env) == "، " * 119
    assert time.monotonic() - started < 2
