"""Exercise the actual provider callback, compiler and bounded event publisher."""

import asyncio
import json
from typing import Any
from unittest.mock import AsyncMock

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply
from lonora_agent import model_runtime, visual_response
from lonora_agent.stream_publication import StreamPublication
from lonora_agent.visual_response import VisualReplyProjector, parse_visual_reply
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_tools.loader import load_tools
from test_teammate_runtime import model_boundary as model_boundary
from test_teammate_runtime import model_context
from test_visual_response import context, document, frame, messages


@pytest.mark.asyncio
async def test_complete_panels_and_following_prose_do_not_wait_for_a_later_panel():
    compiler = VisualReplyProjector(context(), messages())
    first = "First paragraph.\n\n" + frame(document()) + "Independent prose.\n"
    unfinished = first + '```lonora-ui\n{"version":1,'
    preview = await compiler.project(unfinished, partial=True)
    assert preview.text.startswith("First paragraph.\n\n[example]\nEquity: 42 USD\n")
    assert preview.text.endswith("Independent prose.\n") and not preview.errors
    rich = preview.rich_until()
    assert rich and [part["type"] for part in rich["parts"]] == ["text", "ui", "text"]
    assert "lonora-ui" not in preview.text and "version" not in preview.text
    final = await compiler.project(unfinished + "\n```\nStill useful.")
    assert final.text.startswith(preview.text)
    final_rich = final.rich_until()
    assert final.errors and final_rich and final_rich["parts"][1]["type"] == "ui"
    assert "Still useful." in final.text


@pytest.mark.asyncio
async def test_closed_frames_compile_once_across_provider_chunks(monkeypatch: pytest.MonkeyPatch):
    compile_real = visual_response.compile_document
    observed = AsyncMock(side_effect=compile_real)
    monkeypatch.setattr(visual_response, "compile_document", observed)
    compiler = VisualReplyProjector(context(), messages())
    complete = "  Intro.\n\n" + frame(document())
    for tail in ("", "Additional ", "Additional words. "):
        preview = await compiler.project(complete + tail, partial=True)
        assert preview.rich_until() and preview.text.startswith("  Intro.\n\n")
    final = await compiler.project(complete + "Additional words. ")
    assert final.text == preview.text and observed.await_count == 1


@pytest.mark.asyncio
async def test_closing_line_at_provisional_eof_waits_for_its_line_boundary():
    compiler = VisualReplyProjector(context(), messages())
    raw = frame(document()).rstrip()
    preview = await compiler.project(raw, partial=True)
    assert not preview.text and preview.rich_until() is None
    complete = await compiler.project(raw + "\n", partial=True)
    complete_rich = complete.rich_until()
    assert complete_rich and complete_rich["parts"][0]["type"] == "ui"
    final = await compiler.project(raw)
    assert final.text == complete.text


@pytest.mark.asyncio
async def test_protocol_demonstration_inside_a_code_example_remains_code():
    raw = "A code example:\n````text\n" + frame(document()) + "````\n"
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
    raw = frame(document()).replace("```", "~~~")
    answer, rich, errors = await parse_visual_reply(context(), raw, messages())
    assert not errors and rich and "Equity: 42 USD" in answer
    assert "~~~" not in answer


@pytest.mark.asyncio
@pytest.mark.parametrize("hidden", [False, True])
async def test_split_credentials_in_composed_display_never_enter_the_rich_transport(hidden: bool):
    raw = document()
    raw["root"] = {
        "id": "secret-preview",
        "type": "text",
        "visible": not hidden,
        "value": {"op": "concat", "args": ["password", "=", "private-example-value"]},
    }
    compiler = VisualReplyProjector(context(), messages())
    result = await compiler.project(frame(raw))
    answer, rich, errors = result.text, result.rich_until(), result.errors
    assert rich and all(part["type"] == "text" for part in rich["parts"])
    assert errors == ["visual_frame_rejected"]
    assert compiler.diagnostics[0]["code"] == "visual_composed_display_private"
    assert "private-example-value" not in answer


@pytest.mark.asyncio
@pytest.mark.parametrize("marker", ["{{symbol", "{{symbol name}}", "{{{{symbol}}"])
async def test_final_malformed_bindings_are_unavailable_while_code_stays_literal(marker: str):
    raw = f"Entry: {marker}\nOther findings.\n`{marker}`"
    answer, rich, errors = await parse_visual_reply(context(), raw, messages())
    assert rich is None and errors == ["visual_unresolved_text_binding"]
    assert answer == f"Entry: Unavailable\nOther findings.\n`{marker}`"


@pytest.mark.asyncio
async def test_split_markers_in_composed_display_do_not_enter_transport():
    raw = document()
    raw["root"] = {
        "id": "bad",
        "type": "text",
        "value": {"op": "concat", "args": ["{", "{symbol}}"]},
    }
    compiler = VisualReplyProjector(context(), messages())
    result = await compiler.project(frame(raw))
    assert result.errors == ["visual_frame_rejected"]
    assert compiler.diagnostics[0]["code"] == "visual_display_binding_unresolved"
    rich = result.rich_until()
    assert (
        "{{" not in result.text and rich and not any(part["type"] == "ui" for part in rich["parts"])
    )


@pytest.mark.asyncio
async def test_diagnostics_contain_structural_locations_without_model_inputs():
    raw = document()
    raw["root"]["value"] = {"op": "not-real", "args": ["password=private-value"]}
    compiler = VisualReplyProjector(context(), messages())
    projection = await compiler.project(frame(raw))
    assert projection.errors and compiler.diagnostics
    diagnostic = json.dumps(compiler.diagnostics)
    assert "private-value" not in diagnostic and "password" not in diagnostic
    assert "visual_schema_invalid" in diagnostic and "root.value" in diagnostic


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
