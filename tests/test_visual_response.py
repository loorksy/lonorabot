"""The ordinary response compiler admits bounded native UI, never effects."""

import json
from copy import deepcopy
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent import model_runtime
from lonora_agent.public_stream import PublicStream
from lonora_agent.visual_response import (
    compile_document,
    parse_visual_reply,
    read_frame,
    visual_observation_catalog,
)
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_contracts.visual_response import RichContent, VisualDocument
from lonora_db.client import Database
from lonora_db.schema import ArtifactRow, CloudChartRow
from lonora_tools.context import ToolContext
from test_task_runtime import task_db as task_db
from test_teammate_runtime import (
    financial_messages,
    model_context,
)
from test_teammate_runtime import (
    model_boundary as model_boundary,
)


def frame(value: Any) -> str:
    return "```lonora-ui\n" + json.dumps(value) + "\n```\n"


def document(value: Any = 42, mode: str = "example") -> dict[str, Any]:
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


def context(fixture: tuple[Database, str, str, str] | None = None) -> ToolContext:
    if fixture:
        db, owner, agent, thread = fixture
        return cast(
            ToolContext, SimpleNamespace(db=db, owner_id=owner, agent_id=agent, thread_id=thread)
        )
    return cast(ToolContext, SimpleNamespace())


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
    raw = document({"fact": {"call_id": "actual", "path": "/equity"}}, "observed")
    answer, rich, errors = await parse_visual_reply(
        context(), "Summary.\n" + frame(raw) + "Explanation.", messages()
    )
    assert not errors and rich
    assert [part["type"] for part in rich["parts"]] == ["text", "ui", "text"]
    compiled = rich["parts"][1]["document"]
    assert compiled["facts"]["f0"] == {
        "value": 1234.5,
        "source": "account_read",
        "observed_at": "2026-10-25T10:00:00Z",
    }
    assert "Equity: 1234.5 USD" in answer and "lonora-ui" not in answer
    assert RichContent.model_validate(rich).parts
    assert rich["parts"][0]["text"] == "Summary." and rich["parts"][2]["text"] == "Explanation."


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "alteration", ["literal", "old", "path", "failed", "private", "facts", "source"]
)
async def test_untrusted_observations_fall_back_without_breaking_chat(alteration: str):
    history = messages()
    raw = document({"fact": {"call_id": "actual", "path": "/equity"}}, "observed")
    if alteration == "literal":
        cast(dict[str, Any], raw["root"])["value"] = 999999
    if alteration == "old":
        history.append(ModelMessage(role="user", content="New request"))
    if alteration == "path":
        cast(dict[str, Any], raw["root"])["value"]["fact"]["path"] = "/unknown"
    if alteration == "failed":
        history = messages({"status": "failed", "equity": 1234.5})
    if alteration == "private":
        history = messages({"password": "not-for-display"})
        cast(dict[str, Any], raw["root"])["value"]["fact"]["path"] = "/password"
    if alteration == "facts":
        raw["facts"] = {"fake": {"value": 999999, "source": "broker"}}
    if alteration == "source":
        cast(dict[str, Any], raw["root"])["value"] = {"source": "fake"}
    answer, rich, errors = await parse_visual_reply(
        context(), "Useful prose.\n" + frame(raw), history
    )
    assert errors and rich and all(part["type"] != "ui" for part in rich["parts"])
    assert answer.startswith("Useful prose.") and "could not be displayed" in answer
    assert "999999" not in answer and "not-for-display" not in answer


@pytest.mark.asyncio
@pytest.mark.parametrize("body", ["{", "null", "{}", "[1,2]", '{"bad":"' + "x" * 64001 + '"}'])
async def test_bad_and_oversized_frames_are_removed(body: str):
    answer, _, errors = await parse_visual_reply(
        context(), "Safe.\n```lonora-ui\n" + body + "\n```\nAfter.", messages()
    )
    assert errors and "Safe." in answer and "After." in answer and body not in answer


@pytest.mark.asyncio
async def test_unclosed_frame_does_not_expose_raw_output():
    answer, _, errors = await parse_visual_reply(
        context(), "Safe.\n```lonora-ui\n" + json.dumps(document()), messages()
    )
    assert errors and "metric" not in answer and "Safe." in answer


@pytest.mark.asyncio
async def test_finished_frame_missing_terminal_brace_keeps_verified_values_and_controls():
    raw = json.dumps(document({"fact": {"call_id": "actual", "path": "/equity"}}, "observed"))
    answer, rich, errors = await parse_visual_reply(
        context(), "```lonora-ui\n" + raw[:-1] + "\n```\n", messages()
    )
    assert not errors and rich and "1234.5" in answer
    assert rich["parts"][0]["document"]["facts"]["f0"]["value"] == 1234.5


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "raw", ['{"mode":"example', '{"mode":"example",}', '{"root":[}', '{"root":']
)
async def test_terminal_completion_never_invents_strings_values_or_bypasses_schema(raw: str):
    answer, rich, errors = await parse_visual_reply(
        context(), "```lonora-ui\n" + raw + "\n```\n", messages()
    )
    assert errors and rich and all(part["type"] == "text" for part in rich["parts"])
    assert raw not in answer


def test_terminal_delimiter_recovery_preserves_every_value_and_escaped_string():
    expected = {"items": [{"text": 'an escaped " and } ]', "value": 3}]}
    raw = json.dumps(expected)
    assert read_frame(raw[:-3] + "]}}") == expected
    assert read_frame(raw[:-3]) == expected
    assert read_frame(raw + "}") == expected


@pytest.mark.parametrize(
    "raw",
    [
        '{"items":[1},"value":2}',
        '{"items":[1]} false',
        '{"items":[1]} {"other":2}',
        '{"value":"unfinished',
        '{"value":}',
        '{"value":1,}',
    ],
)
def test_terminal_recovery_cannot_rewrite_interior_syntax_or_invent_values(raw: str):
    with pytest.raises(ValueError):
        read_frame(raw)


@pytest.mark.asyncio
@pytest.mark.parametrize("missing", ["call", "path"])
async def test_missing_cell_is_unavailable_while_independently_observed_cells_survive(missing: str):
    known = {"fact": {"call_id": "actual", "path": "/equity"}}
    unknown = {"fact": {"call_id": "unknown", "path": "/equity"}}
    if missing == "path":
        unknown = {"fact": {"call_id": "actual", "path": "/missing"}}
    raw = {
        "version": 1,
        "mode": "observed",
        "root": {
            "id": "comparison",
            "type": "table",
            "fields": [
                {"key": "known", "label": "Verified"},
                {"key": "missing", "label": "Missing"},
            ],
            "rows": [{"known": known, "missing": unknown}],
        },
    }
    answer, rich, errors = await parse_visual_reply(context(), frame(raw), messages())
    assert not errors and rich
    compiled = rich["parts"][0]["document"]
    assert compiled["root"]["rows"] == [{"known": {"source": "f0"}, "missing": None}]
    assert len(compiled["facts"]) == 1 and "1234.5 | —" in answer


@pytest.mark.asyncio
@pytest.mark.parametrize("bad", ["private", "failed", "object", "nonfinite"])
async def test_good_fact_cannot_launder_a_forbidden_observation(bad: str):
    result: dict[str, Any] = {"equity": 1234.5, "password": "private-value"}
    path = "/password"
    if bad == "failed":
        result["nested"] = {"ok": False, "equity": 999}
        path = "/nested/equity"
    if bad == "object":
        result["nested"] = {"equity": 999}
        path = "/nested"
    if bad == "nonfinite":
        result["bad"] = float("inf")
        path = "/bad"
    raw = document(
        {
            "op": "add",
            "args": [
                {"fact": {"call_id": "actual", "path": "/equity"}},
                {"fact": {"call_id": "actual", "path": path}},
            ],
        },
        "observed",
    )
    answer, rich, errors = await parse_visual_reply(context(), frame(raw), messages(result))
    assert errors and rich and all(part["type"] == "text" for part in rich["parts"])
    assert "1234.5" not in answer and "private-value" not in answer


@pytest.mark.asyncio
async def test_array_length_counts_only_actual_returned_items():
    raw = document({"fact": {"call_id": "actual", "path": "/files/length"}}, "observed")
    compiled = await compile_document(context(), raw, messages({"files": [{"size": 3}, {}]}))
    assert compiled["facts"]["f0"]["value"] == 2
    compiled = await compile_document(context(), raw, messages({"files": []}))
    assert compiled["facts"]["f0"]["value"] == 0
    with pytest.raises(ValueError):
        await compile_document(context(), raw, messages({"files": "not-an-array"}))
    compiled = await compile_document(context(), raw, messages({"files": {"length": 7}}))
    assert compiled["facts"]["f0"]["value"] == 7


def test_fragmented_provider_stream_never_exposes_visual_fence_or_payload():
    stream = PublicStream(set(), set(), enabled=True)
    prefix = "This is a useful introductory paragraph.\n"
    emitted = stream.feed(prefix)
    for character in frame(document()) + "Afterwards prose.":
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


@pytest.mark.asyncio
async def test_private_display_values_scrubbed_without_damaging_resource_ids(
    task_db: tuple[Database, str, str, str],
):
    db, owner, agent, thread = task_db
    identity = str(uuid4())
    async with db.sessions() as session, session.begin():
        session.add(
            ArtifactRow(
                id=identity,
                owner_id=owner,
                agent_id=agent,
                thread_id=thread,
                payload={"media_type": "image/png"},
            )
        )
    raw: dict[str, Any] = {
        "version": 1,
        "mode": "example",
        "root": {
            "id": "image",
            "type": "image",
            "artifact_id": identity,
            "label": "password=abcd123456",
        },
    }
    result = await compile_document(context(task_db), raw, messages())
    assert result["root"]["artifact_id"] == identity
    assert "abcd123456" not in result["root"]["label"]
    cast(dict[str, Any], raw["root"])["artifact_id"] = str(uuid4())
    with pytest.raises(ValueError, match="visual_resource_not_available"):
        await compile_document(context(task_db), raw, messages())


@pytest.mark.asyncio
async def test_cross_thread_chart_is_rejected(task_db: tuple[Database, str, str, str]):
    db, owner, agent, _ = task_db
    identity = str(uuid4())
    async with db.sessions() as session, session.begin():
        session.add(CloudChartRow(id=identity, owner_id=owner, agent_id=agent, thread_id=None))
    raw: dict[str, Any] = {
        "version": 1,
        "mode": "example",
        "root": {
            "id": "open",
            "type": "button",
            "label": "Open",
            "action": {"kind": "open_chart", "resource_id": identity},
        },
    }
    with pytest.raises(ValueError, match="visual_resource_not_available"):
        await compile_document(context(task_db), raw, messages())


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
):
    published, usage = model_boundary
    raw = (
        "A concise explanation.\n" + (frame(document()) if native else "") + "No trade is executed."
    )
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
    if native:
        assert reply.rich_content and reply.rich_content["parts"][1]["type"] == "ui"
    else:
        assert reply.rich_content is None and reply.text == raw
    visible = "".join(data["text"] for kind, data in published if kind == "run.delta")
    assert visible == reply.text and "lonora-ui" not in visible
    assert ("Equity: 42 USD" in visible) == native


@pytest.mark.asyncio
async def test_model_visual_cannot_bypass_unverified_financial_receipt(
    model_boundary: tuple[list[tuple[str, dict[str, Any]]], AsyncMock],
):
    complete = AsyncMock(
        return_value=(
            ModelReply(text="Executed successfully.\n" + frame(document())),
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
    raw = document({"fact": {"call_id": "actual", "path": path}}, "observed")
    answer, rich, errors = await parse_visual_reply(context(), frame(raw), messages(result))
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
    raw = document({"fact": {"call_id": "actual", "path": "/equity"}}, "observed")
    answer, rich, errors = await parse_visual_reply(context(), frame(raw), history)
    assert not errors and rich and "1234.5" in answer
    assert rich["parts"][0]["document"]["facts"]["f0"]["value"] == 1234.5


@pytest.mark.asyncio
async def test_source_metadata_is_privacy_filtered_too():
    raw = document({"fact": {"call_id": "actual", "path": "/equity"}}, "observed")
    compiled = await compile_document(
        context(), raw, messages({"equity": 1234.5, "observed_at": "password=opaque-secret"})
    )
    assert compiled["facts"]["f0"]["observed_at"] == "[REDACTED]"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "opening,closing",
    [("```LONORA-UI", "```"), ("````lonora-ui", "````"), ("``` lonora-ui", "```")],
)
async def test_markdown_fence_variations_never_expose_native_payload(opening: str, closing: str):
    prefix = "Here is a concise useful summary.\n"
    reply = prefix + opening + "\n" + json.dumps(document()) + "\n" + closing + "\n"
    stream = PublicStream(set(), set(), enabled=True)
    emitted = ""
    for character in reply:
        stream.last_publish = 0
        emitted += stream.feed(character)
    assert "lonora" not in emitted.lower() and "metric" not in emitted
    answer, rich, errors = await parse_visual_reply(context(), reply, messages())
    assert rich and not errors
    assert "Equity: 42 USD" in answer and "metric" not in answer


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


@pytest.mark.parametrize(
    "expression,expected",
    [
        ({"op": "round", "args": [2.5]}, 3),
        ({"op": "round", "args": [-1.5]}, -1),
        ({"op": "round", "args": [1.005, 2]}, 1.01),
        ({"op": "round", "args": [1.005, -1]}, None),
        ({"op": "round", "args": [1.005, 1.5]}, None),
        ({"op": "eq", "args": [True, 1]}, False),
        ({"op": "eq", "args": [1, 1.0]}, True),
        ({"op": "gt", "args": ["z", "a"]}, None),
        ({"op": "mul", "args": [1e308, 1e308]}, None),
    ],
)
def test_legacy_text_calculations_match_native_scalar_semantics(expression: Any, expected: Any):
    from lonora_agent.visual_response import text_projection

    text = text_projection(document(expression))
    actual = text.split("Equity: ", 1)[1].removesuffix(" USD")
    if expected is None:
        assert actual == "—"
    elif isinstance(expected, bool):
        assert actual == str(expected)
    else:
        assert float(actual) == expected
