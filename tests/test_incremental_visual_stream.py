"""Exercise the actual provider callback, the v2 card compiler and the bounded publisher."""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock, Mock

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply
from lonora_agent import model_runtime, visual_response
from lonora_agent.stream_publication import StreamPublication
from lonora_agent.visual_response import VisualReplyProjector, parse_visual_reply
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_tools.loader import load_tools
from test_teammate_runtime import model_boundary as model_boundary
from test_teammate_runtime import model_context
from test_visual_response import FALLBACK, context, frame, messages


def text_card(text: str, when: str | None = None) -> str:
    """A v2 card showing one Text node."""
    block: dict[str, Any] = {"type": "Text", "text": text}
    if when is not None:
        block["when"] = when
    lines = [
        {"v": 2, "kind": "summary", "title": "Preview", "icon": "info"},
        block,
        {"why": "A short preview.", "fallback": "A preview."},
    ]
    return "\n".join(json.dumps(line) for line in lines)


@pytest.mark.asyncio
async def test_a_complete_card_and_following_prose_do_not_wait_for_a_later_fence():
    compiler = VisualReplyProjector(context(), messages())
    first = "First paragraph.\n\n" + frame() + "Independent prose.\n"
    unfinished = first + '```lonora-ui\n{"v":2,'
    preview = await compiler.project(unfinished, partial=True)
    assert preview.text.startswith("First paragraph.\n\n") and FALLBACK in preview.text
    assert preview.text.endswith("Independent prose.\n") and not preview.errors
    rich = preview.rich_until()
    assert rich and [part["type"] for part in rich["parts"]] == ["text", "ui", "text"]
    assert "lonora-ui" not in preview.text and '"v"' not in preview.text
    final = await compiler.project(unfinished + "\n```\nStill useful.")
    assert final.text.startswith(preview.text)
    final_rich = final.rich_until()
    # One card per reply: the second fence is dropped (its fallback, if any, stays text).
    assert final_rich and final_rich["parts"][1]["type"] == "ui"
    assert "Still useful." in final.text
    assert any(item["code"] == "interface_extra" for item in compiler.diagnostics)


@pytest.mark.asyncio
async def test_closed_frames_compile_once_across_provider_chunks(monkeypatch: pytest.MonkeyPatch):
    observed = Mock(side_effect=visual_response.compile_card)
    monkeypatch.setattr(visual_response, "compile_card", observed)
    compiler = VisualReplyProjector(context(), messages())
    complete = "  Intro.\n\n" + frame()
    for tail in ("", "Additional ", "Additional words. "):
        preview = await compiler.project(complete + tail, partial=True)
        assert preview.rich_until() and preview.text.startswith("  Intro.\n\n")
    final = await compiler.project(complete + "Additional words. ")
    assert final.text == preview.text and observed.call_count == 1


@pytest.mark.asyncio
async def test_closing_line_at_provisional_eof_waits_for_its_line_boundary():
    compiler = VisualReplyProjector(context(), messages())
    raw = frame().rstrip()
    preview = await compiler.project(raw, partial=True)
    assert not preview.text
    complete = await compiler.project(raw + "\n", partial=True)
    complete_rich = complete.rich_until()
    assert complete_rich and complete_rich["parts"][0]["type"] == "ui"
    assert "building" not in complete_rich["parts"][0]
    final = await compiler.project(raw)
    assert final.text == complete.text


@pytest.mark.asyncio
async def test_protocol_demonstration_inside_a_code_example_remains_code():
    raw = "A code example:\n````text\n" + frame() + "````\n"
    assert await parse_visual_reply(context(), raw, messages()) == (raw, None, [])
    compiler = VisualReplyProjector(context(), messages())
    assert (await compiler.project(raw, partial=True)).text == raw


@pytest.mark.asyncio
async def test_unbound_prose_fields_are_unavailable_without_inventing_trading_values():
    raw = "Known findings.\n\nEntry: {{entry}}; stop: {{sl}}; target: {{tp1}}.\n\nOther findings."
    answer, rich, errors = await parse_visual_reply(context(), raw, messages())
    assert rich is None and errors == ["visual_unresolved_text_binding"]
    assert "{{" not in answer and answer.count("Unavailable") == 3
    assert "Known findings." in answer and "Other findings." in answer


@pytest.mark.asyncio
async def test_literal_template_code_and_ordinary_json_are_preserved():
    raw = 'Template syntax: `{{symbol}}`.\n```javascript\nconst template = "{{entry}}";\n```\n{"normal": "JSON"}\n'
    assert await parse_visual_reply(context(), raw, messages()) == (raw, None, [])


@pytest.mark.asyncio
async def test_unfinished_prose_binding_does_not_escape_incremental_admission():
    compiler = VisualReplyProjector(context(), messages())
    pending = await compiler.project("Entry: {{entr", partial=True)
    assert pending.text == "Entry: "
    final = await compiler.project("Entry: {{entry}} ")
    assert final.text == "Entry: Unavailable "


@pytest.mark.asyncio
async def test_tilde_native_frame_has_the_same_validated_projection():
    raw = frame().replace("```", "~~~")
    answer, rich, errors = await parse_visual_reply(context(), raw, messages())
    assert not errors and rich and FALLBACK in answer
    assert "~~~" not in answer


@pytest.mark.asyncio
@pytest.mark.parametrize("hidden", [False, True])
async def test_split_credentials_in_composed_display_never_enter_the_rich_transport(hidden: bool):
    body = text_card("{'password' + '=' + 'private-example-value'}", "false" if hidden else None)
    compiler = VisualReplyProjector(context(), messages())
    result = await compiler.project(frame(body))
    answer, rich, errors = result.text, result.rich_until(), result.errors
    assert rich and all(part["type"] == "text" for part in rich["parts"])
    assert errors == ["visual_frame_rejected"]
    assert any(item["code"] == "card_fallback_private" for item in compiler.diagnostics)
    assert "private-example-value" not in answer and "private-example-value" not in json.dumps(rich)


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", ["{{symbol", "{{symbol name}}", "{{{{symbol}}"])
async def test_final_malformed_bindings_are_unavailable_while_code_stays_literal(marker: str):
    raw = f"Entry: {marker}\nOther findings.\n`{marker}`"
    answer, rich, errors = await parse_visual_reply(context(), raw, messages())
    assert rich is None and errors == ["visual_unresolved_text_binding"]
    assert answer == f"Entry: Unavailable\nOther findings.\n`{marker}`"


@pytest.mark.asyncio
@pytest.mark.parametrize("text", ["Entry: {{symbol}}", "**{{ entry }}** at {$x}"])
async def test_split_markers_in_composed_display_do_not_enter_transport(text: str):
    compiler = VisualReplyProjector(context(), messages())
    result = await compiler.project(frame(text_card(text)))
    assert result.errors == ["visual_frame_rejected"]
    assert any(item["code"] == "card_fallback_binding" for item in compiler.diagnostics)
    rich = result.rich_until()
    assert (
        "{{" not in result.text and rich and not any(part["type"] == "ui" for part in rich["parts"])
    )


@pytest.mark.asyncio
async def test_diagnostics_contain_structural_locations_without_model_inputs():
    body = text_card("{@NotReal('password=private-value')}")
    body = body.replace('{"type": "Text"', '{"type": "Note", "text": "Kept"}\n{"type": "Text"')
    compiler = VisualReplyProjector(context(), messages())
    await compiler.project(frame(body))
    assert compiler.diagnostics
    diagnostic = json.dumps(compiler.diagnostics)
    assert "private-value" not in diagnostic and "password" not in diagnostic
    assert "block_dropped" in diagnostic


@pytest.mark.asyncio
async def test_provider_reads_do_not_wait_for_a_slow_event_store():
    entered, release = asyncio.Event(), asyncio.Event()
    received: list[str] = []

    async def write(value: str) -> None:
        entered.set()
        await release.wait()
        received.append(value)

    publication = StreamPublication(write)
    await publication.offer("First provider chunk. ")
    await asyncio.wait_for(entered.wait(), 1)
    # This callback must return while the store is still blocked.
    await asyncio.wait_for(publication.offer("Second provider chunk. "), 0.1)
    release.set()
    await publication.finish()
    assert received[-1] == "First provider chunk. Second provider chunk. "


@pytest.mark.asyncio
async def test_cancelled_publication_cannot_write_after_a_new_generation():
    entered = asyncio.Event()
    committed: list[str] = []

    async def write(value: str) -> None:
        entered.set()
        await asyncio.Event().wait()
        committed.append(value)

    publication = StreamPublication(write)
    await publication.offer("Old generation. ")
    await asyncio.wait_for(entered.wait(), 1)
    await publication.cancel()
    await publication.offer("Late old chunk. ")
    assert not committed


@pytest.mark.asyncio
async def test_advertised_financial_tools_do_not_suppress_an_ordinary_live_answer(
    model_boundary: tuple[list[tuple[str, dict[str, Any]]], AsyncMock],
):
    published, _ = model_boundary
    early, finish = asyncio.Event(), asyncio.Event()
    answer = "I can review buy and sell setups while the current candle is still forming. "

    async def complete(*args: Any, **kwargs: Any):
        await kwargs["on_delta"](answer)
        early.set()
        await finish.wait()
        return ModelReply(text=answer), ModelSelection(provider="openai", model="offline")

    work = asyncio.create_task(
        model_runtime.model_turn(
            model_context(complete),
            [ModelMessage(role="user", content="What can you do?")],
            load_tools().definitions(),
            Capability.CONVERSATION,
        )
    )
    try:
        await asyncio.wait_for(early.wait(), 1)
        for _ in range(50):
            if any(kind == "run.delta" for kind, _ in published):
                break
            await asyncio.sleep(0.01)
        assert not work.done()
        assert "".join(data["text"] for kind, data in published if kind == "run.delta") == answer
    finally:
        finish.set()
        await work
