"""The v2 projector and compiler: line streaming, facts, the card's account, option checks,
the delivery row, budget and deterministic repair (docs/genui.md)."""

import json
import re
from collections.abc import Callable
from contextlib import asynccontextmanager
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast

import pytest
from lonora_adapter_kit.types import ModelMessage, ToolCall
from lonora_agent.visual_response import VisualReplyProjector
from lonora_contracts.visual_response import RichContent
from lonora_tools.context import ToolContext

A01 = (Path(__file__).parent / "fixtures/genui/documents/valid/a01-alert.lonora-ui").read_text()
LEAD = "جهّزت التنبيه من رسالتك؛ راجع الشرط ثم أنشئه.\n"
QUOTES = {"c1": ("XAUUSD", "2368.40"), "c2": ("XAGUSD", "28.92"), "c3": ("EURUSD", "1.0842")}


class _Agent:
    def __init__(self, account: str | None = None, symbol: str | None = None):
        self.trading_account_id, self.trading_symbol = account, symbol


class _Session:
    def __init__(self, agent: _Agent | None):
        self.agent = agent

    async def get(self, model: Any, identity: str) -> Any:
        return self.agent

    async def scalars(self, statement: Any) -> list[Any]:
        return []  # one account: no other enabled connection


class _Db:
    def __init__(self, agent: _Agent | None = None):
        self.agent = agent

    @asynccontextmanager
    async def sessions(self):
        yield _Session(self.agent)


def context(agent: _Agent | None = None) -> ToolContext:
    return cast(
        ToolContext,
        SimpleNamespace(
            db=_Db(agent),
            owner_id="o",
            agent_id="agent-1",
            thread_id="t",
            lease=SimpleNamespace(run_id="run-1"),
        ),
    )


def messages(
    quotes: dict[str, tuple[str, str]] = QUOTES, account: str = "acc-1"
) -> list[ModelMessage]:
    calls = [
        ToolCall(id=call, name="market_quote", arguments={"account_id": account, "symbol": symbol})
        for call, (symbol, _bid) in quotes.items()
    ]
    result = [
        ModelMessage(role="user", content="نبّهني إذا صعد الذهب فوق 2400"),
        ModelMessage(role="assistant", content="", tool_calls=calls),
    ]
    for call, (symbol, bid) in quotes.items():
        result.append(
            ModelMessage(
                role="tool",
                tool_call_id=call,
                content=json.dumps(
                    {
                        "symbol": symbol,
                        "bid": bid,
                        "ask": bid,
                        "observed_at": "2026-11-10T09:00:00Z",
                        "source": "simulation",
                    }
                ),
            )
        )
    return result


def reply(body: str = A01) -> str:
    return LEAD + "```lonora-ui\n" + body.rstrip("\n") + "\n```\n"


Edit = Callable[[str], str]


def edits(*items: Edit) -> list[Edit]:
    """A parametrized list of card edits, typed so each lambda's argument is the card text."""
    return list(items)


async def project(
    text: str,
    *,
    agent: _Agent | None = None,
    history: list[ModelMessage] | None = None,
    partial: bool = False,
):
    projector = VisualReplyProjector(context(agent), history or messages())
    projection = await projector.project(text, partial=partial)
    return projection, projector


@pytest.mark.asyncio
async def test_a01_compiles_with_facts_account_and_delivery_row() -> None:
    projection, projector = await project(reply())
    rich = projection.rich_until()
    assert rich is not None
    RichContent.model_validate(rich)
    text, card = rich["parts"]
    assert text == {"type": "text", "text": LEAD.strip()}
    document = card["document"]
    assert document["account_id"] == "acc-1" and document["agent_id"] == "agent-1"
    assert document["facts"]["xau"]["value"] == 2368.4
    assert document["facts"]["xau"]["observed_at"] == "2026-11-10T09:00:00Z"
    assert [b["type"] for b in document["blocks"]] == [
        "Segmented",
        "Segmented",
        "Number",
        "Text",
        "Note",
        "Delivery",
        "Button",
    ]
    assert document["blocks"][5] == {"type": "Delivery", "channels": ["app"]}
    assert document["blocks"][6]["action"]["lock"] is True
    # content = lead + blank line + fallback; no typed market price in the fallback.
    assert projection.text == LEAD + "\n" + document["fallback"] + "\n"
    assert "2368" not in projection.text
    assert not [d for d in projector.diagnostics if d["code"].startswith("card_")]


@pytest.mark.asyncio
async def test_streaming_shows_the_skeleton_then_blocks_never_a_partial_line() -> None:
    full = reply()
    fence = full.index("```lonora-ui") + len("```lonora-ui\n")
    seen: list[int] = []
    for end in range(fence + 5, len(full), 37):
        projection, _ = await project(full[:end], partial=True)
        rich = projection.rich_until()
        cards = [p for p in (rich or {"parts": []})["parts"] if p["type"] == "ui"]
        if cards:
            assert cards[0]["building"] is True
            seen.append(len(cards[0]["document"]["blocks"]))
            assert "```" not in projection.text and '"v":2' not in projection.text
    assert seen and seen == sorted(seen) and seen[-1] >= 5
    final, _ = await project(full)
    assert "building" not in cast(dict[str, Any], final.rich_until())["parts"][1]


@pytest.mark.asyncio
async def test_mislabelled_identity_option_falls_back() -> None:
    bad = A01.replace('"value":"XAUUSD","label":"الذهب"', '"value":"XAUUSD","label":"الفضة"')
    projection, projector = await project(reply(bad))
    assert projection.rich_until() is None or all(
        p["type"] == "text" for p in cast(dict[str, Any], projection.rich_until())["parts"]
    )
    assert "أستطيع إنشاء التنبيه" in projection.text
    assert any(d["code"] == "card_fallback_reachable" for d in projector.diagnostics)


@pytest.mark.asyncio
async def test_unquoted_option_is_dropped_and_accepted_short_names() -> None:
    quotes = {"c1": QUOTES["c1"], "c2": QUOTES["c2"]}
    body = A01.replace('"label":"الذهب"', '"label":"ذهب"')
    projection, projector = await project(reply(body), history=messages(quotes))
    card = cast(dict[str, Any], projection.rich_until())["parts"][1]["document"]
    assert [o["value"] for o in card["blocks"][0]["options"]] == ["XAUUSD", "XAGUSD"]
    assert any(d["code"] == "option_unverified" for d in projector.diagnostics)


@pytest.mark.asyncio
async def test_quote_on_a_second_account_falls_back() -> None:
    history = messages()
    history[1].tool_calls[2].arguments["account_id"] = "acc-2"
    projection, projector = await project(reply(), history=history)
    assert all(p["type"] == "text" for p in (projection.rich_until() or {"parts": []})["parts"])
    assert any(d["code"] == "card_fallback_account" for d in projector.diagnostics)


@pytest.mark.asyncio
async def test_fixed_market_agent_offers_only_its_pair() -> None:
    projection, projector = await project(reply(), agent=_Agent("acc-1", "XAUUSD"))
    card = cast(dict[str, Any], projection.rich_until())["parts"][1]["document"]
    assert [o["value"] for o in card["blocks"][0]["options"]] == ["XAUUSD"]
    assert any(d["code"] == "option_out_of_scope" for d in projector.diagnostics)


@pytest.mark.parametrize(
    "intent", ["trade.execute", "risk.apply", "order_place", "grant.widen", "focus.log"]
)
@pytest.mark.asyncio
async def test_denied_or_unlisted_primary_send_falls_back(intent: str) -> None:
    projection, projector = await project(reply(A01.replace('"alert.create"', f'"{intent}"')))
    assert all(p["type"] == "text" for p in (projection.rich_until() or {"parts": []})["parts"])
    assert any(d["code"] == "action_refused" for d in projector.diagnostics)


@pytest.mark.asyncio
async def test_secondary_refused_button_is_dropped_never_shown_disabled() -> None:
    extra = (
        '{"type":"Button","label":"افتح","action":{"do":"open","url":"https://evil.example/x"}}\n'
    )
    body = A01.replace('{"why"', extra + '{"why"')
    projection, projector = await project(reply(body))
    card = cast(dict[str, Any], projection.rich_until())["parts"][1]["document"]
    assert not any(b.get("label") == "افتح" for b in card["blocks"])
    assert any(d["code"] == "action_refused" for d in projector.diagnostics)


@pytest.mark.asyncio
async def test_tampered_send_data_cannot_carry_server_set_or_extra_fields() -> None:
    body = A01.replace(
        '"data":{"symbol":"$symbol"', '"data":{"account_id":"other","symbol":"$symbol"'
    )
    projection, _ = await project(reply(body))
    assert all(p["type"] == "text" for p in (projection.rich_until() or {"parts": []})["parts"])


@pytest.mark.asyncio
async def test_observed_card_without_any_resolved_fact_falls_back() -> None:
    projection, _ = await project(reply(), history=messages({}))
    assert all(p["type"] == "text" for p in (projection.rich_until() or {"parts": []})["parts"])


@pytest.mark.asyncio
async def test_missing_why_and_fallback_get_defaults() -> None:
    body = A01.rsplit("\n", 2)[0] + "\n"
    projection, projector = await project(reply(body))
    card = cast(dict[str, Any], projection.rich_until())["parts"][1]["document"]
    assert card["why"] and card["fallback"].startswith("**تنبيه سعر**")
    codes = {d["code"] for d in projector.diagnostics}
    assert {"why_default", "fallback_generated"} <= codes


@pytest.mark.asyncio
async def test_second_card_is_dropped_with_its_fallback_as_text() -> None:
    second = '{"v":2,"kind":"summary","title":"x","icon":"check"}\n{"type":"Text","text":"y"}\n{"why":"w","fallback":"الثانية"}'
    text = reply() + "\n```lonora-ui\n" + second + "\n```\n"
    projection, projector = await project(text)
    parts = cast(dict[str, Any], projection.rich_until())["parts"]
    assert sum(p["type"] == "ui" for p in parts) == 1
    assert "الثانية" in projection.text
    assert any(d["code"] == "interface_extra" for d in projector.diagnostics)


@pytest.mark.asyncio
async def test_over_budget_blocks_fold_but_the_send_stays_last() -> None:
    notes = "".join(f'{{"type":"Text","text":"سطر {i}"}}\n' for i in range(5))
    body = A01.replace('{"type":"Button"', notes + '{"type":"Button"')
    projection, projector = await project(reply(body))
    blocks = cast(dict[str, Any], projection.rich_until())["parts"][1]["document"]["blocks"]
    assert [b["type"] for b in blocks][-3:] == ["More", "Delivery", "Button"]
    assert any(d["code"] == "budget_folded" for d in projector.diagnostics)


def test_v2_prompt_block_is_bounded_generated_and_the_only_one() -> None:
    from lonora_agent.genui_capabilities import capabilities
    from lonora_agent.skills.visual_policy import (
        MAX_GENUI_GUIDANCE_CHARS,
        VISUAL_END,
        VISUAL_MARKER,
        native_visual_policy,
    )

    block = native_visual_policy()
    assert block.startswith(VISUAL_MARKER) and block.endswith(VISUAL_END)
    assert len(block) <= MAX_GENUI_GUIDANCE_CHARS
    for part in ("<lonora_answer_shape>", "<lonora_ui_rules>", "alert.create", "XAUUSD Gold"):
        assert part in block
    # English only (owner rule): no Arabic outside the instrument names the compiler matches.
    names = block.index("Instrument names")
    rest = block[:names] + block[block.index("\n", names) :]
    assert not re.search("[\u0600-\u06ff]", rest)
    assert "{vocabulary}" not in block and "{teaching}" not in block and "<!--" not in block
    assert capabilities().block() == (
        "<lonora_ui_capabilities>\nintents: ask, alert.create, alert.off\ndelivery: app\n"
        "go: market, tasks, usage, files, agents\n"
        "timezone: UTC · language: ar\n</lonora_ui_capabilities>"
    )


@pytest.mark.asyncio
async def test_a_summary_with_a_literal_watch_id_compiles() -> None:
    history = messages()
    history.insert(
        2,
        ModelMessage(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="w1", name="watch_create", arguments={"symbol": "XAUUSD"})],
        ),
    )
    history.insert(
        3,
        ModelMessage(
            role="tool", tool_call_id="w1", content='{"id":"47a32ccd-c721-5382-b3b1-9ba4d335db1e"}'
        ),
    )
    body = "\n".join(
        [
            '{"v":2,"kind":"summary","title":"Alert active","icon":"check"}',
            '{"type":"KeyValue","rows":[["Asset","Gold"]]}',
            '{"type":"Button","label":"Stop alert","action":{"do":"send","intent":"alert.off","data":{"watch_id":"47a32ccd-c721-5382-b3b1-9ba4d335db1e"}}}',
            '{"why":"w","fallback":"f"}',
        ]
    )
    projection, _ = await project(
        "The alert is active.\n```lonora-ui\n" + body + "\n```\n", history=history
    )
    card = cast(dict[str, Any], projection.rich_until())["parts"][1]["document"]
    assert card["blocks"][1]["action"]["data"]["watch_id"].startswith("47a32ccd")


@pytest.mark.asyncio
async def test_observed_without_any_fact_drops_the_mode_not_the_card() -> None:
    body = "\n".join(
        [
            '{"v":2,"kind":"diagram","title":"How it works","icon":"nodes","mode":"observed"}',
            '{"type":"Note","text":"Your request starts here."}',
            '{"why":"w","fallback":"f"}',
        ]
    )
    projection, projector = await project("Here is the path:\n```lonora-ui\n" + body + "\n```\n")
    card = cast(dict[str, Any], projection.rich_until())["parts"][1]["document"]
    assert "mode" not in card and any(d["code"] == "mode_checked" for d in projector.diagnostics)


@pytest.mark.asyncio
async def test_a_typed_market_value_makes_the_card_fall_back() -> None:
    # A receipt that types the silver quote it read, instead of citing it with @Fact.
    body = A01.replace(
        '{"type":"Text","tone":"muted"',
        '{"type":"KeyValue","rows":[["Now","28.92"]]}\n{"type":"Text","tone":"muted"',
    )
    projection, projector = await project(reply(body))
    assert all(p["type"] == "text" for p in (projection.rich_until() or {"parts": []})["parts"])
    assert any(d["code"] == "card_fallback_typed_fact" for d in projector.diagnostics)
    # The owner's own 2400 is theirs to show.
    owned = A01.replace(
        '{"type":"Text","tone":"muted"',
        '{"type":"KeyValue","rows":[["Target","2400"]]}\n{"type":"Text","tone":"muted"',
    )
    projection, _ = await project(reply(owned))
    rich = projection.rich_until()
    assert rich and any(p["type"] == "ui" for p in rich["parts"])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "edit",
    edits(
        # A templated head title assembles a private id only when rendered.
        lambda body: body.replace('"title":"تنبيه سعر"', '"title":"{$tid}"').replace(
            '"calc":{', '"calc":{"tid":"\'0f1e2d3c-4b5a-6978\'+\'-8a9b-0c1d2e3f4a5b\'",'
        ),
        # So does a templated sub.
        lambda body: body.replace('"sub":"يصلك عند تحقق الشرط"', '"sub":"{$tid}"').replace(
            '"calc":{', '"calc":{"tid":"\'0f1e2d3c-4b5a-6978\'+\'-8a9b-0c1d2e3f4a5b\'",'
        ),
        # A plain-string option label is rendered too.
        lambda body: body.replace(
            '{"type":"Text","tone":"muted"',
            '{"type":"Segmented","bind":"pick","label":"x","options":'
            '["0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"]}\n{"type":"Text","tone":"muted"',
        ),
        # A value an option's `also` selects is rendered as the client shows it.
        lambda body: body.replace(
            '"also":{"price":null}}', '"also":{"price":null,"tag":"0f1e2d3c-4b5a-6978"}}', 1
        ).replace(
            '{"type":"Text","tone":"muted"',
            '{"type":"Note","text":"{$tag + \'-8a9b-0c1d2e3f4a5b\'}"}\n'
            '{"type":"Text","tone":"muted"',
        ),
    ),
)
async def test_the_privacy_guard_reads_rendered_strings(edit: Edit) -> None:
    """S2: the client renders templates and scalar labels, so the guard does too."""
    projection, projector = await project(reply(edit(A01)))
    assert all(p["type"] == "text" for p in (projection.rich_until() or {"parts": []})["parts"])
    assert any(d["code"] == "card_fallback_private" for d in projector.diagnostics), [
        d["code"] for d in projector.diagnostics
    ]


@pytest.mark.asyncio
async def test_the_card_takes_its_currency_from_account_read() -> None:
    """E1: ``account_read`` nests the account under ``account``; money on the card is
    labelled with that account's currency."""
    history = messages()
    history.insert(
        1,
        ModelMessage(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="a1", name="account_read", arguments={"account_id": "acc-1"})],
        ),
    )
    history.insert(
        2,
        ModelMessage(
            role="tool",
            tool_call_id="a1",
            content=json.dumps(
                {"account": {"account_id": "acc-1", "currency": "EUR", "balance": "10000"}}
            ),
        ),
    )
    projection, _ = await project(reply(), history=history)
    rich = projection.rich_until()
    assert rich is not None
    assert rich["parts"][-1]["document"]["currency"] == "EUR"


async def _stopped(blocks: int, phase: str = "cancelled") -> dict[str, Any] | None:
    """A Run whose stream holds a card still building, settled by Stop or failure."""
    from lonora_db.schema import RunRow
    from lonora_db.streaming import STREAM_KEY, settle_stream, stream_data

    lines = A01.strip().split("\n")
    partial = LEAD + "```lonora-ui\n" + "\n".join(lines[: 2 + blocks]) + "\n"
    projection, _ = await project(partial, partial=True)
    rich = projection.rich_until()
    assert rich is not None and rich["parts"][-1].get("building")
    row = RunRow(model_metadata={STREAM_KEY: {"phase": "streaming", "rich_content": rich}})
    settle_stream(row, phase)
    stream = stream_data(row)
    return stream.get("rich_content") if stream else None


@pytest.mark.asyncio
async def test_stop_mid_build_stores_the_built_blocks_with_cut() -> None:
    """E2: Stop keeps the blocks built so far, marked ``cut``; never a building skeleton."""
    rich = await _stopped(3)
    assert rich is not None
    part = rich["parts"][-1]
    assert part["type"] == "ui" and part["cut"] == 3 and not part.get("building")
    assert len(part["document"]["blocks"]) == 3


@pytest.mark.asyncio
async def test_stop_before_any_block_shows_the_fallback_and_failure_never_builds() -> None:
    """E2: ``cut = 0`` hides the card and shows its fallback; a failed turn's card is
    its fallback too (it was not the owner's Stop)."""
    for rich in (await _stopped(0), await _stopped(3, "failed")):
        assert rich is not None
        assert [p["type"] for p in rich["parts"]] == ["text", "text"]
        assert not any(p.get("building") for p in rich["parts"])


@pytest.mark.asyncio
async def test_a_link_in_a_cards_send_is_never_the_owners_link() -> None:
    """An ``open`` URL is allowed only when the owner typed it or a tool returned it; a
    card's send (``[owner_via_card …]``) is card words, never the owner's (review)."""
    link = "https://example.com/gold-report"
    body = A01.replace(
        '{"type":"Text","tone":"muted"',
        '{"type":"Button","label":"التقرير","action":{"do":"open","url":"'
        + link
        + '"}}\n{"type":"Text","tone":"muted"',
    )

    async def opens(owner: str) -> bool:
        history = messages()
        history[0] = ModelMessage(role="user", content=owner)
        projection, _ = await project(reply(body), history=history)
        rich = projection.rich_until()
        assert rich is not None
        from lonora_contracts.genui import walk

        document = rich["parts"][-1]["document"]
        return any(
            node.get("action", {}).get("url") == link for _p, node in walk(document["blocks"])
        )

    assert await opens("نبّهني إذا صعد الذهب فوق 2400 " + link)
    assert not await opens("[owner_via_card «تنبيه سعر»]\nافتح " + link)


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "edit",
    edits(
        # Inside template braces.
        lambda b: b.replace(
            '{"type":"Text","tone":"muted"',
            '{"type":"Note","text":"السعر {2368.40}"}\n{"type":"Text","tone":"muted"',
        ),
        # A calc literal and an expression constant.
        lambda b: b.replace('"calc":{', '"calc":{"x":2368.4,'),
        lambda b: b.replace("@Fact('xau')", "2368.40", 1),
        # An option's also, and an option label.
        lambda b: b.replace('"also":{"price":2400}', '"also":{"price":2368.4}'),
        lambda b: b.replace('"label":"يصعد فوق"', '"label":"يصعد فوق 2,368.40"'),
        # Arabic-Indic digits.
        lambda b: b.replace(
            '{"type":"Text","tone":"muted"',
            '{"type":"Note","text":"السعر ٢٬٣٦٨٫٤٠"}\n{"type":"Text","tone":"muted"',
        ),
    ),
)
async def test_typed_market_values_are_caught_wherever_the_card_types_them(edit: Edit) -> None:
    projection, projector = await project(reply(edit(A01)))
    assert all(p["type"] == "text" for p in (projection.rich_until() or {"parts": []})["parts"])
    assert any(d["code"] == "card_fallback_typed_fact" for d in projector.diagnostics)


@pytest.mark.asyncio
async def test_a_year_or_id_from_a_quote_is_not_a_market_value() -> None:
    """Only price-like quote and account fields count: the card may type the year the
    quote's timestamp also carries (review, rule 2 false positive)."""
    body = A01.replace(
        '{"type":"Text","tone":"muted"',
        '{"type":"Note","text":"خطة 2026"}\n{"type":"Text","tone":"muted"',
    )
    projection, projector = await project(reply(body))
    rich = projection.rich_until()
    assert rich is not None and rich["parts"][-1]["type"] == "ui"
    assert not any(d["code"] == "card_fallback_typed_fact" for d in projector.diagnostics)


@pytest.mark.asyncio
async def test_a_fixed_market_agents_card_on_another_account_falls_back() -> None:
    """A fixed-market agent's card reads only its own account (review): quotes read on
    any other account make the card fall back as ``option_out_of_scope``."""
    projection, projector = await project(reply(), agent=_Agent("acc-2", "XAUUSD"))
    assert all(p["type"] == "text" for p in (projection.rich_until() or {"parts": []})["parts"])
    assert any(d["code"] == "option_out_of_scope" for d in projector.diagnostics)


@pytest.mark.asyncio
async def test_a_second_card_after_a_fallback_is_still_dropped() -> None:
    """One card per reply even when the first fell back to text (review)."""
    first = A01.replace('"alert.create"', '"trade.execute"')  # falls back
    second = '{"v":2,"kind":"summary","title":"x","icon":"check"}\n{"type":"Text","text":"y"}\n{"why":"w","fallback":"الثانية"}'
    text = reply(first) + "\n```lonora-ui\n" + second + "\n```\n"
    projection, projector = await project(text)
    parts = (projection.rich_until() or {"parts": []})["parts"]
    assert not any(p["type"] == "ui" for p in parts)
    assert any(d["code"] == "interface_extra" for d in projector.diagnostics)


@pytest.mark.asyncio
async def test_the_skeleton_shows_as_soon_as_the_fence_opens() -> None:
    """Before the head line is complete the card already shows as a building skeleton
    (review), never nothing."""
    projection, _ = await project(LEAD + '```lonora-ui\n{"v":2,"kind":"for', partial=True)
    rich = projection.rich_until()
    assert rich is not None
    part = rich["parts"][-1]
    assert part["type"] == "ui" and part["building"] is True
    assert part["document"]["blocks"] == []
    RichContent.model_validate(rich)


@pytest.mark.asyncio
async def test_an_alert_card_on_an_account_the_server_cannot_name_falls_back() -> None:
    """With several accounts, an alert card's bubble must name its account (docs/genui.md §7)."""
    from lonora_agent.genui_capabilities import capabilities
    from lonora_agent.genui_compile import AgentScope, CardError, compile_card
    from lonora_contracts.genui import parse_lines

    scope = AgentScope(agent_id="agent-1", several_accounts=True, named_accounts=frozenset())
    with pytest.raises(CardError, match="card_fallback_account_unnamed"):
        compile_card(
            parse_lines(A01, final=True), messages(), scope, capabilities(), set(), final=True
        )
    named = AgentScope(
        agent_id="agent-1", several_accounts=True, named_accounts=frozenset({"acc-1"})
    )
    compile_card(parse_lines(A01, final=True), messages(), named, capabilities(), set(), final=True)


@pytest.mark.asyncio
async def test_a_card_built_on_a_calc_chain_falls_back_or_stays_bounded_never_crashes() -> None:
    """Review round 4: the nested-list calc chain compiles quickly to a bounded card."""
    import time

    chain = (
        '"a":"@Join(@Range(0,200),\'xxxxxxx\')",'
        + '"b":"['
        + ",".join(["$a"] * 120)
        + ']","c":"['
        + ",".join(["$b"] * 120)
        + ']",'
    )
    body = A01.replace('"calc":{', '"calc":{' + chain).replace(
        '{"type":"Text","tone":"muted"',
        '{"type":"Note","text":"{$c}"}\n{"type":"Text","tone":"muted"',
    )
    started = time.monotonic()
    projection, _ = await project(reply(body))
    assert time.monotonic() - started < 5
    rich = projection.rich_until()
    assert rich is not None
    assert len(json.dumps(rich, ensure_ascii=False)) < 64_000


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "edit",
    edits(
        # An option without a label shows its value (UiCard optionList).
        lambda b: b.replace(
            '{"type":"Text","tone":"muted"',
            '{"type":"Segmented","bind":"pick","label":"x","options":'
            '[{"value":"0f1e2d3c-4b5a-6978-8a9b-0c1d2e3f4a5b"}]}\n{"type":"Text","tone":"muted"',
        ),
        # A branch no sampled state renders is still read as written.
        lambda b: b.replace(
            '"title":"تنبيه سعر"', "\"title\":\"{$f ? '/workspace/k' : 'T'}\""
        ).replace('"state":{', '"state":{"f":false,'),
    ),
)
async def test_the_privacy_guard_reads_what_the_client_shows_and_every_branch(edit: Edit) -> None:
    projection, projector = await project(reply(edit(A01)))
    assert all(p["type"] == "text" for p in (projection.rich_until() or {"parts": []})["parts"])
    assert any(d["code"] == "card_fallback_private" for d in projector.diagnostics), [
        d["code"] for d in projector.diagnostics
    ]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "field",
    [
        "stop_loss",
        "take_profit",
        "level",
        "reference_price",
        "last_swing_high",
        "previous_swing_low",
        "atr",
    ],
)
async def test_typed_market_fields_beyond_quotes_are_caught(field: str) -> None:
    """Review round 4: a stop, target, watch level, swing or ATR read this turn is a market
    value too; typing it instead of citing it makes the card fall back."""
    history = messages()
    history.insert(
        1,
        ModelMessage(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(id="p1", name="market_positions", arguments={"account_id": "acc-1"})
            ],
        ),
    )
    history.insert(
        2,
        ModelMessage(
            role="tool", tool_call_id="p1", content=json.dumps({"items": [{field: "2351.75"}]})
        ),
    )
    body = A01.replace(
        '{"type":"Text","tone":"muted"',
        '{"type":"Note","text":"المستوى 2,351.75"}\n{"type":"Text","tone":"muted"',
    )
    projection, projector = await project(reply(body), history=history)
    assert all(p["type"] == "text" for p in (projection.rich_until() or {"parts": []})["parts"])
    assert any(d["code"] == "card_fallback_typed_fact" for d in projector.diagnostics)


def _card(*blocks: str, fallback: bool = True) -> str:
    close = '{"why":"w","fallback":"f"}' if fallback else '{"why":"w"}'
    head = '{"v":2,"kind":"calculator","title":"Size","icon":"chart"}'
    data = '{"state":{"x":1}}'
    return "\n".join([head, data, *blocks, close])


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "block",
    [
        '{"type":"Slider","bind":"x","label":"Lots","show":"{$x} lots password=opaque-secret"}',
        '{"type":"Button","label":"Copy","action":{"do":"copy","text":"api_key: opaque-secret"}}',
        '{"type":"Slider","bind":"x","label":"Lots","show":"at {{price}}"}',
        '{"type":"Button","label":"Copy","action":{"do":"copy","text":"buy at {{price}}"}}',
    ],
)
async def test_a_slider_readout_and_copied_text_pass_the_same_guards_as_shown_text(
    block: str,
) -> None:
    """Slider `show` is displayed and a copy action's text reaches the clipboard (and the
    card's notice): private values and unfilled placeholders never pass through them."""
    projection, projector = await project(reply(_card(block)))
    rich = cast(dict[str, Any], projection.rich_until())
    assert all(part["type"] != "ui" for part in rich["parts"])
    codes = {d["code"] for d in projector.diagnostics}
    assert codes & {"card_fallback_private", "card_fallback_binding"}
    assert "opaque-secret" not in json.dumps(rich)


@pytest.mark.asyncio
async def test_a_list_valued_mode_is_dropped_never_a_crash() -> None:
    body = A01.replace('"mode":"observed"', '"mode":["observed"]')
    projection, projector = await project(reply(body))
    rich = cast(dict[str, Any], projection.rich_until())
    document = rich["parts"][1]["document"]
    assert "mode" not in document
    assert any(d["code"] == "prop_dropped" for d in projector.diagnostics)


@pytest.mark.asyncio
async def test_the_generated_fallback_reads_stat_markdown_and_badge() -> None:
    body = _card(
        '{"type":"Stat","label":"Risk","value":"{$x} %"}',
        '{"type":"Markdown","text":"- one\\n- two"}',
        '{"type":"Badge","text":"Estimate"}',
        fallback=False,
    )
    projection, _ = await project(reply(body))
    document = cast(dict[str, Any], projection.rich_until())["parts"][1]["document"]
    fallback = document["fallback"]
    assert "**Risk:** 1 %" in fallback and "- one" in fallback and "Estimate" in fallback


def trade_history(status: str) -> list[ModelMessage]:
    """A request in which trade_execute answered with an operation in ``status``."""
    history = messages()
    history.insert(
        2,
        ModelMessage(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="t1", name="trade_execute", arguments={"symbol": "XAUUSD"})],
        ),
    )
    history.insert(
        3,
        ModelMessage(
            role="tool",
            tool_call_id="t1",
            content=json.dumps(
                {
                    "results": [{"operation_id": "op-1", "status": status, "broker_id": "50071"}],
                    "operation_id": "op-1",
                    "status": status,
                    "broker_id": "50071",
                }
            ),
        ),
    )
    return history


def trade_card(path: str) -> str:
    return "\n".join(
        [
            '{"v":2,"kind":"summary","title":"Order","icon":"check","mode":"observed"}',
            '{"facts":{"ticket":{"call":"t1","path":"' + path + '"}}}',
            '{"type":"KeyValue","rows":[["Ticket","@Fact(ticket)"]]}',
            '{"why":"w","fallback":"f"}',
        ]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["ambiguous", "submitted", "reserved", "resolved"])
@pytest.mark.parametrize("path", ["/broker_id", "/results/0/broker_id"])
async def test_an_agent_cannot_draw_an_unconfirmed_operation_as_done(
    status: str, path: str
) -> None:
    """10.3 "The agent can never draw 'confirmed' itself" and 6.10: a fact bound to an
    operation the broker has not confirmed resolves to nothing, so the card falls back."""
    projection, projector = await project(
        "Done.\n```lonora-ui\n" + trade_card(path) + "\n```\n", history=trade_history(status)
    )
    assert all(p["type"] == "text" for p in (projection.rich_until() or {"parts": []})["parts"])
    assert any(d["code"].startswith("card_fallback") for d in projector.diagnostics)


@pytest.mark.asyncio
async def test_a_confirmed_operation_can_be_cited() -> None:
    projection, _ = await project(
        "Done.\n```lonora-ui\n" + trade_card("/broker_id") + "\n```\n",
        history=trade_history("confirmed"),
    )
    card = cast(dict[str, Any], projection.rich_until())["parts"][1]["document"]
    assert card["facts"]["ticket"]["value"] == 50071 and card["kind"] == "summary"


@pytest.mark.asyncio
async def test_the_old_receipt_kind_is_not_a_card_kind() -> None:
    """The generic kind no longer bears the fixed Execution Receipt's name (10.3)."""
    body = (
        '{"v":2,"kind":"receipt","title":"Alert active","icon":"check"}\n{"why":"w","fallback":"f"}'
    )
    projection, _ = await project("Done.\n```lonora-ui\n" + body + "\n```\n")
    assert all(p["type"] == "text" for p in (projection.rich_until() or {"parts": []})["parts"])


def history_with(name: str, result: dict[str, Any]) -> list[ModelMessage]:
    history = messages()
    history.insert(
        2,
        ModelMessage(
            role="assistant", content="", tool_calls=[ToolCall(id="t1", name=name, arguments={})]
        ),
    )
    history.insert(3, ModelMessage(role="tool", tool_call_id="t1", content=json.dumps(result)))
    return history


async def falls_back(body: str, history: list[ModelMessage]) -> bool:
    projection, _ = await project("Done.\n```lonora-ui\n" + body + "\n```\n", history=history)
    return all(p["type"] == "text" for p in (projection.rich_until() or {"parts": []})["parts"])


TWO_RESULTS = {
    "results": [
        {"operation_id": "op-1", "status": "confirmed", "broker_id": "50071"},
        {"operation_id": "op-2", "status": "ambiguous", "broker_id": "50072"},
    ]
}


@pytest.mark.asyncio
async def test_a_whole_list_with_an_unconfirmed_operation_is_never_shown() -> None:
    body = trade_card("/results")
    assert await falls_back(body, history_with("trade_close_positions", TWO_RESULTS))


@pytest.mark.asyncio
async def test_a_journal_excerpt_of_an_unconfirmed_operation_shows_nothing() -> None:
    excerpt = {
        "operation_id": "op-9",
        "request": {"action": "buy", "price": "2401.35", "volume": "0.1"},
        "result": {"operation_id": "op-9", "status": "ambiguous"},
        "submitted_at": "2026-11-12T09:00:00Z",
    }
    for path in ("/request/price", "/submitted_at", "/request"):
        assert await falls_back(trade_card(path), history_with("trade_record_read", excerpt))


@pytest.mark.asyncio
async def test_one_unconfirmed_fact_makes_the_whole_card_fall_back() -> None:
    body = "\n".join(
        [
            '{"v":2,"kind":"summary","title":"Orders","icon":"check","mode":"observed"}',
            '{"facts":{"a":{"call":"t1","path":"/results/0/broker_id"},'
            '"b":{"call":"t1","path":"/results/1/broker_id"}}}',
            '{"type":"KeyValue","rows":[["A","@Fact(a)"],["B","@Fact(b)"]]}',
            '{"why":"w","fallback":"f"}',
        ]
    )
    assert await falls_back(body, history_with("trade_close_positions", TWO_RESULTS))


@pytest.mark.asyncio
async def test_a_trades_ticket_and_price_are_cited_never_typed() -> None:
    result: dict[str, Any] = {
        "operation_id": "op-1",
        "status": "ambiguous",
        "broker_id": "50071",
        "details": {"price": "2401.35", "volume": "0.10"},
    }
    body = "\n".join(
        [
            '{"v":2,"kind":"summary","title":"Order","icon":"check"}',
            '{"type":"KeyValue","rows":[["Ticket","50071"],["Price","2,401.35"]]}',
            '{"why":"w","fallback":"f"}',
        ]
    )
    assert await falls_back(body, history_with("trade_execute", result))


@pytest.mark.asyncio
async def test_no_card_at_all_beside_an_unconfirmed_trade() -> None:
    """10.3: after a trade the broker has not confirmed, a card that cites nothing can
    still not read as done; the reply carries text only."""
    body = "\n".join(
        [
            '{"v":2,"kind":"summary","title":"تم تنفيذ الصفقة","icon":"check"}',
            '{"type":"Badge","text":"مؤكَّد","tone":"good"}',
            '{"type":"KeyValue","rows":[["الحالة","نُفّذت بنجاح"]]}',
            '{"why":"w","fallback":"f"}',
        ]
    )
    for name in ("trade_execute", "trade_close_positions"):
        ambiguous = {"operation_id": "op-1", "status": "ambiguous"}
        assert await falls_back(body, history_with(name, ambiguous))
        assert await falls_back(body, history_with(name, TWO_RESULTS))
    # A confirmed trade does not hold the card back.
    confirmed = {"operation_id": "op-1", "status": "confirmed", "broker_id": "50071"}
    assert not await falls_back(body, history_with("trade_execute", confirmed))


@pytest.mark.asyncio
async def test_the_length_of_a_list_with_an_unconfirmed_operation_is_not_shown() -> None:
    assert await falls_back(
        trade_card("/results/length"), history_with("trade_record_history", TWO_RESULTS)
    )
