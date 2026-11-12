"""The ordinary response compiler admits bounded lonora-ui v2 cards, never effects.

v2 is the only generated interface (mandate 10.1.3): every ``lonora-ui`` fence is a v2 card,
and a v1 document is never compiled from a model reply any more; the v1 contract remains
only to validate stored v1 messages (the contract tests below)."""

import json
from copy import deepcopy
from typing import Any, cast
from unittest.mock import AsyncMock

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent import model_runtime
from lonora_agent.public_stream import PublicStream
from lonora_agent.visual_response import parse_visual_reply, visual_observation_catalog
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_contracts.visual_response import RichContent, VisualDocument
from test_genui_projector import context
from test_teammate_runtime import (
    financial_messages,
    model_context,
)
from test_teammate_runtime import (
    model_boundary as model_boundary,
)

FALLBACK = "Your equity, read from the account."


def card(path: str = "/equity", call: str = "actual") -> str:
    """A v2 card showing one account fact."""
    lines = [
        {"v": 2, "kind": "receipt", "title": "Equity", "icon": "chart", "mode": "observed"},
        {"facts": {"eq": {"call": call, "path": path}}},
        {"type": "KeyValue", "rows": [["Equity", "{@Fact('eq')}"]]},
        {"why": "One figure with its source.", "fallback": FALLBACK},
    ]
    return "\n".join(json.dumps(line) for line in lines)


def frame(body: str | None = None) -> str:
    return "```lonora-ui\n" + (card() if body is None else body) + "\n```\n"


def document(value: Any = 42, mode: str = "example") -> dict[str, Any]:
    """A stored v1 document (rendering only)."""
    return {
        "version": 1,
        "mode": mode,
        "root": {
            "id": "metric",
            "type": "metric",
            "label": "Equity",
            "value": value,
            "unit": "USD",
        },
    }


def messages(result: Any = None) -> list[ModelMessage]:
    return [
        ModelMessage(role="user", content="How is my account?"),
        ModelMessage(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="actual", name="account_read", arguments={})],
        ),
        ModelMessage(
            role="tool",
            tool_call_id="actual",
            content=json.dumps(
                result
                if result is not None
                else {"equity": 1234.5, "observed_at": "2026-10-25T10:00:00Z"}
            ),
        ),
    ]


@pytest.mark.asyncio
async def test_observation_resolves_actual_current_call_and_preserves_mixed_order():
    answer, rich, errors = await parse_visual_reply(
        context(), "Summary.\n" + frame() + "Explanation.", messages()
    )
    assert not errors and rich
    assert [part["type"] for part in rich["parts"]] == ["text", "ui", "text"]
    compiled = rich["parts"][1]["document"]
    assert compiled["v"] == 2
    assert compiled["facts"]["eq"] == {
        "value": 1234.5,
        "source": "account_read",
        "observed_at": "2026-10-25T10:00:00Z",
    }
    assert FALLBACK in answer and "lonora-ui" not in answer
    assert RichContent.model_validate(rich).parts
    assert rich["parts"][0]["text"] == "Summary." and rich["parts"][2]["text"] == "Explanation."


@pytest.mark.asyncio
async def test_a_v1_document_is_never_compiled_from_a_reply():
    answer, rich, errors = await parse_visual_reply(
        context(), "Useful prose.\n```lonora-ui\n" + json.dumps(document()) + "\n```\n", messages()
    )
    assert errors and rich and all(part["type"] != "ui" for part in rich["parts"])
    assert answer.startswith("Useful prose.") and "metric" not in answer


@pytest.mark.asyncio
@pytest.mark.parametrize("alteration", ["old", "path", "call", "failed", "private"])
async def test_untrusted_observations_fall_back_without_breaking_chat(alteration: str):
    history = messages()
    body = card()
    if alteration == "old":
        history.append(ModelMessage(role="user", content="New request"))
    if alteration == "path":
        body = card("/unknown")
    if alteration == "call":
        body = card(call="invented")
    if alteration == "failed":
        history = messages({"status": "failed", "equity": 1234.5})
    if alteration == "private":
        history = messages({"password": "not-for-display", "equity": 1})
        body = card("/password")
    answer, rich, errors = await parse_visual_reply(
        context(), "Useful prose.\n" + frame(body), history
    )
    assert errors and rich and all(part["type"] != "ui" for part in rich["parts"])
    assert answer.startswith("Useful prose.")
    assert "1234.5" not in answer and "not-for-display" not in answer


@pytest.mark.asyncio
@pytest.mark.parametrize("body", ["{", "null", "{}", "[1,2]", '{"bad":"' + "x" * 64001 + '"}'])
async def test_bad_and_oversized_frames_are_removed(body: str):
    answer, _, errors = await parse_visual_reply(
        context(), "Safe.\n```lonora-ui\n" + body + "\n```\nAfter.", messages()
    )
    assert errors and "Safe." in answer and "After." in answer and body not in answer


@pytest.mark.asyncio
async def test_unclosed_frame_does_not_expose_raw_output():
    answer, _, _ = await parse_visual_reply(context(), "Safe.\n```lonora-ui\n" + card(), messages())
    assert "Safe." in answer and '"v"' not in answer and "@Fact" not in answer


def test_fragmented_provider_stream_never_exposes_visual_fence_or_payload():
    stream = PublicStream(set(), set(), enabled=True)
    prefix = "This is a useful introductory paragraph.\n"
    emitted = stream.feed(prefix)
    for character in frame() + "Afterwards prose.":
        stream.last_publish = 0
        emitted += stream.feed(character)
    assert emitted == prefix and stream.sent == prefix


def test_model_can_address_actual_transport_ids_without_new_observations_or_presentation_rule():
    history = messages()
    catalog = visual_observation_catalog(history)
    assert '"call_id":"actual"' in catalog and '"tool":"account_read"' in catalog
    assert "1234.5" not in catalog and "plain prose remains valid" in catalog
    assert not visual_observation_catalog(messages({"ok": False, "equity": 1234.5}))
    assert not visual_observation_catalog(
        [*history, ModelMessage(role="user", content="A new question")]
    )


@pytest.mark.asyncio
async def test_plain_reply_is_byte_identical_and_needs_no_database():
    text = "Equity means your balance plus floating profit or loss."
    assert await parse_visual_reply(context(), text, messages()) == (text, None, [])


@pytest.mark.parametrize("mutation", ["script", "trade", "nested", "arity", "initial", "nan"])
def test_bounded_contract_rejects_executable_and_malformed_composition(mutation: str):
    raw = deepcopy(document())
    if mutation == "script":
        cast(dict[str, Any], raw["root"])["onClick"] = "alert(1)"
    if mutation == "trade":
        raw["root"] = {
            "id": "trade",
            "type": "button",
            "label": "Buy",
            "action": {"kind": "trade_execute"},
        }
    if mutation == "nested":
        cast(dict[str, Any], raw["root"])["value"] = {"op": "abs", "args": [1, 2]}
    if mutation == "arity":
        cast(dict[str, Any], raw["root"])["value"] = {"op": "div", "args": [1]}
    if mutation == "initial":
        raw["root"] = {"id": "input", "type": "slider", "state_key": "missing"}
    if mutation == "nan":
        cast(dict[str, Any], raw["root"])["value"] = float("nan")
    with pytest.raises(ValueError):
        VisualDocument.model_validate(raw)


@pytest.mark.asyncio
@pytest.mark.parametrize("native", [False, True])
async def test_existing_model_turn_respects_plain_or_mixed_output_without_second_generation(
    model_boundary: tuple[list[tuple[str, dict[str, Any]]], AsyncMock],
    native: bool,
    monkeypatch: pytest.MonkeyPatch,
):
    published, usage = model_boundary
    from lonora_agent.genui_compile import AgentScope
    from lonora_agent.visual_response import VisualReplyProjector

    async def scope(self: VisualReplyProjector) -> AgentScope:
        return AgentScope(agent_id="agent")  # one unbound agent; the boundary has no database

    monkeypatch.setattr(VisualReplyProjector, "agent_scope", scope)
    raw = "A concise explanation.\n" + (frame() if native else "") + "No trade is executed."
    complete = AsyncMock(
        return_value=(ModelReply(text=raw), ModelSelection(provider="openai", model="offline"))
    )
    reply, _ = await model_runtime.model_turn(
        model_context(complete), messages(), [], Capability.CONVERSATION
    )
    assert complete.await_count == usage.await_count == 1
    assert complete.await_args is not None
    supplied = complete.await_args.args[1]
    assert any('"call_id":"actual"' in item.content for item in supplied if item.role == "system")
    # The per-request capabilities block is always there: v2 is the only interface.
    assert any("<lonora_ui_capabilities>" in item.content for item in supplied)
    if native:
        assert reply.rich_content and reply.rich_content["parts"][1]["type"] == "ui"
    else:
        assert reply.rich_content is None and reply.text == raw
    visible = "".join(data["text"] for kind, data in published if kind == "run.delta")
    assert visible == reply.text and "lonora-ui" not in visible
    assert (FALLBACK in visible) == native


@pytest.mark.asyncio
async def test_model_visual_cannot_bypass_unverified_financial_receipt(
    model_boundary: tuple[list[tuple[str, dict[str, Any]]], AsyncMock],
):
    complete = AsyncMock(
        return_value=(
            ModelReply(text="Executed successfully.\n" + frame()),
            ModelSelection(provider="openai", model="offline"),
        )
    )
    reply, _ = await model_runtime.model_turn(
        model_context(complete), financial_messages(False), [], Capability.CONVERSATION
    )
    assert reply.rich_content is None and "التحقق المستقل" in reply.text
    assert complete.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "result,path",
    [
        ({"ok": False, "equity": 1234.5}, "/equity"),
        ({"account": {"ok": False, "equity": 1234.5}}, "/account/equity"),
        ({"api_key": "opaque-sensitive-value"}, "/api_key"),
        ({"apiKey": "opaque-sensitive-value"}, "/apiKey"),
        ({"access_key": "opaque-sensitive-value"}, "/access_key"),
    ],
)
async def test_failed_envelopes_and_secret_source_paths_cannot_be_presented(result: Any, path: str):
    answer, rich, errors = await parse_visual_reply(context(), frame(card(path)), messages(result))
    assert errors and rich
    assert all(part["type"] != "ui" for part in rich["parts"])
    assert "1234.5" not in answer and "opaque-sensitive-value" not in answer


@pytest.mark.asyncio
async def test_internal_image_observation_does_not_reset_real_request_evidence():
    history = messages()
    history.append(
        ModelMessage(
            role="user",
            context_origin="tool_observation",
            content="Image observation associated with the actual tool exchange.",
        )
    )
    _, rich, errors = await parse_visual_reply(context(), frame(), history)
    assert not errors and rich
    assert rich["parts"][0]["document"]["facts"]["eq"]["value"] == 1234.5


@pytest.mark.asyncio
async def test_source_metadata_is_privacy_filtered_too():
    _, rich, _ = await parse_visual_reply(
        context(), frame(), messages({"equity": 1234.5, "observed_at": "password=opaque-secret"})
    )
    assert rich
    observed = rich["parts"][0]["document"]["facts"]["eq"]["observed_at"]
    assert "opaque-secret" not in observed


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "opening,closing",
    [("```LONORA-UI", "```"), ("````lonora-ui", "````"), ("``` lonora-ui", "```")],
)
async def test_markdown_fence_variations_never_expose_native_payload(opening: str, closing: str):
    prefix = "Here is a concise useful summary.\n"
    reply = prefix + opening + "\n" + card() + "\n" + closing + "\n"
    stream = PublicStream(set(), set(), enabled=True)
    emitted = ""
    for character in reply:
        stream.last_publish = 0
        emitted += stream.feed(character)
    assert "lonora" not in emitted.lower() and "@Fact" not in emitted
    answer, rich, errors = await parse_visual_reply(context(), reply, messages())
    assert rich and not errors
    assert FALLBACK in answer and "@Fact" not in answer


@pytest.mark.parametrize("text", [" ", "Request {{unknown}}", "Request {{amount", "Request }}"])
def test_follow_up_actions_reject_dead_or_unknown_state_templates(text: str):
    raw = {
        "version": 1,
        "mode": "example",
        "root": {
            "id": "button",
            "type": "button",
            "label": "Request",
            "action": {"kind": "follow_up", "text": text},
        },
    }
    with pytest.raises(ValueError):
        VisualDocument.model_validate(raw)


@pytest.mark.parametrize("where", ["node", "field", "vertex"])
def test_prototype_reserved_keys_cannot_pass_server_but_fail_client(where: str):
    raw: dict[str, Any] = {
        "version": 1,
        "mode": "example",
        "root": {"id": "root", "type": "text", "text": "Example"},
    }
    if where == "node":
        raw["root"]["id"] = "constructor"
    elif where == "field":
        raw["root"] = {
            "id": "table",
            "type": "table",
            "fields": [{"key": "constructor", "label": "Field"}],
            "rows": [],
        }
    else:
        raw["root"] = {
            "id": "diagram",
            "type": "diagram",
            "vertices": [{"id": "constructor", "label": "Vertex"}],
            "edges": [],
        }
    with pytest.raises(ValueError):
        VisualDocument.model_validate(raw)
