"""OpenAI's Responses API adapter (VISION Amendment 4; the model-catalog specification,
section 3), against a fake transport: no request leaves the process.

The stream shapes follow OpenAI's documented events and what api.openai.com answered
during the adapter's live check (an ``error`` event nests its error object).
"""

import json
from collections.abc import Callable
from typing import Any

import httpx
import pytest
from lonora_adapter_kit.model_errors import FailureReason, ModelProviderError
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_adapters.models.openai_responses import OpenAIResponsesAdapter

KEY = "fixture-not-a-real-key"
QUOTE = ToolDefinition(
    name="quote_read",
    description="Read a symbol's current quote.",
    parameters={
        "type": "object",
        "properties": {"symbol": {"type": "string"}, "depth": {"type": "integer"}},
        "required": ["symbol"],
    },
)
ASK = [
    ModelMessage(role="system", content="Policy one."),
    ModelMessage(role="system", content="Policy two."),
    ModelMessage(role="user", content="What is gold doing?"),
]
# The ChatGPT plan's preview limits: none of these may be sent.
PLAN_UNSUPPORTED = {
    "background",
    "conversation",
    "max_output_tokens",
    "max_tool_calls",
    "metadata",
    "moderation",
    "prompt",
    "prompt_cache_retention",
    "previous_response_id",
    "safety_identifier",
    "temperature",
    "top_logprobs",
    "top_p",
    "truncation",
    "user",
}


def sse(*events: dict[str, Any]) -> str:
    """Server-sent events as OpenAI writes them: an ``event:`` line, then ``data:``."""
    return "".join(
        "event: " + event["type"] + "\ndata: " + json.dumps(event) + "\n\n" for event in events
    )


def started() -> list[dict[str, Any]]:
    response: dict[str, Any] = {"id": "resp_1", "status": "in_progress", "output": []}
    return [
        {"type": "response.created", "response": response},
        {"type": "response.in_progress", "response": response},
    ]


def completed(usage: dict[str, Any] | None = None) -> dict[str, Any]:
    return {
        "type": "response.completed",
        "response": {
            "id": "resp_1",
            "status": "completed",
            "incomplete_details": None,
            "usage": usage or {"input_tokens": 10, "output_tokens": 2},
        },
    }


def incomplete(reason: str = "max_output_tokens") -> dict[str, Any]:
    return {
        "type": "response.incomplete",
        "response": {
            "id": "resp_1",
            "status": "incomplete",
            "incomplete_details": {"reason": reason},
            "usage": {"input_tokens": 10, "output_tokens": 256},
        },
    }


def text(*chunks: str) -> list[dict[str, Any]]:
    return [
        {"type": "response.output_text.delta", "item_id": "msg_1", "delta": chunk}
        for chunk in chunks
    ]


def call(call_id: str, name: str, arguments: str, **extra: Any) -> dict[str, Any]:
    return {
        "type": "response.output_item.done",
        "output_index": 1,
        "item": {
            "type": "function_call",
            "id": "fc_" + call_id,
            "call_id": call_id,
            "name": name,
            "arguments": arguments,
            "status": "completed",
            **extra,
        },
    }


class Server:
    """Records each request and answers with one scripted response."""

    def __init__(self, answer: httpx.Response | Callable[[httpx.Request], httpx.Response]):
        self.answer = answer
        self.seen: list[httpx.Request] = []

    def handle(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        return self.answer(request) if callable(self.answer) else self.answer

    @property
    def body(self) -> dict[str, Any]:
        return json.loads(self.seen[-1].content)


def streamed(*events: dict[str, Any]) -> httpx.Response:
    return httpx.Response(200, text=sse(*events), headers={"content-type": "text/event-stream"})


async def run(
    server: Server,
    messages: list[ModelMessage] = ASK,
    tools: list[ToolDefinition] | None = None,
    *,
    chatgpt_plan: bool = False,
    max_output_tokens: int | None = 512,
    deltas: list[str] | None = None,
    allow_empty: bool = False,
) -> ModelReply:
    async def on_delta(chunk: str) -> None:
        assert deltas is not None
        deltas.append(chunk)

    async with httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as client:
        adapter = OpenAIResponsesAdapter(KEY, client, chatgpt_plan=chatgpt_plan)
        return await adapter.complete(
            "gpt-fixture",
            messages,
            tools or [],
            max_output_tokens=max_output_tokens,
            on_delta=on_delta if deltas is not None else None,
            allow_empty=allow_empty,
        )


async def failure(server: Server, **options: Any) -> ModelProviderError:
    with pytest.raises(ModelProviderError) as caught:
        await run(server, **options)
    return caught.value


# --- Requests ------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_text_turn_streams_its_deltas_and_reports_usage_with_cached_tokens() -> None:
    server = Server(
        streamed(
            *started(),
            *text("Gold ", "is range-bound."),
            completed(
                {
                    "input_tokens": 1200,
                    "input_tokens_details": {"cached_tokens": 1024},
                    "output_tokens": 9,
                    "output_tokens_details": {"reasoning_tokens": 4},
                }
            ),
        )
    )
    deltas: list[str] = []
    reply = await run(server, deltas=deltas)
    assert reply.text == "Gold is range-bound." and deltas == ["Gold ", "is range-bound."]
    assert reply.tool_calls == []
    usage = reply.usage
    assert (usage.input_tokens, usage.output_tokens, usage.cached_tokens) == (1200, 9, 1024)
    assert reply.provider_metadata == {"response_id": "resp_1", "finish_reason": "stop"}
    [request] = server.seen
    assert request.method == "POST" and str(request.url) == "https://api.openai.com/v1/responses"
    assert request.headers["authorization"] == "Bearer " + KEY
    body = server.body
    # Stateless and streamed; system messages become instructions, never system items.
    assert body == {
        "model": "gpt-fixture",
        "instructions": "Policy one.\n\nPolicy two.",
        "input": [{"role": "user", "content": "What is gold doing?"}],
        "stream": True,
        "store": False,
        "max_output_tokens": 512,
    }


@pytest.mark.asyncio
async def test_a_turn_without_a_delta_callback_still_streams() -> None:
    server = Server(streamed(*started(), *text("Ready."), completed()))
    reply = await run(server, max_output_tokens=None)
    assert reply.text == "Ready."
    assert server.body["stream"] is True and "max_output_tokens" not in server.body


@pytest.mark.asyncio
async def test_one_and_several_tool_calls_carry_their_json_arguments() -> None:
    one = Server(
        streamed(*started(), call("call_a", "quote_read", '{"symbol": "XAUUSD"}'), completed())
    )
    reply = await run(one, tools=[QUOTE])
    assert reply.tool_calls == [
        ToolCall(id="call_a", name="quote_read", arguments={"symbol": "XAUUSD"})
    ]
    assert one.body["tools"] == [
        {
            "type": "function",
            "name": "quote_read",
            "description": "Read a symbol's current quote.",
            "parameters": QUOTE.parameters,
            # Optional arguments stay optional.
            "strict": False,
        }
    ]
    several = Server(
        streamed(
            *started(),
            *text("Reading both."),
            call("call_a", "quote_read", '{"symbol": "XAUUSD"}'),
            call("call_b", "quote_read", '{"symbol": "EURUSD", "depth": 5}'),
            completed(),
        )
    )
    reply = await run(several, tools=[QUOTE])
    assert reply.text == "Reading both."
    assert [(c.id, c.arguments) for c in reply.tool_calls] == [
        ("call_a", {"symbol": "XAUUSD"}),
        ("call_b", {"symbol": "EURUSD", "depth": 5}),
    ]


@pytest.mark.asyncio
async def test_a_tool_result_turn_sends_function_calls_and_their_outputs() -> None:
    server = Server(streamed(*started(), *text("Gold is at 2650."), completed()))
    history = [
        *ASK,
        ModelMessage(role="assistant", content="Hello."),
        ModelMessage(
            role="assistant",
            content="",
            tool_calls=[
                ToolCall(id="call_a", name="quote_read", arguments={"symbol": "XAUUSD"}),
                # A call another provider answered earlier keeps its own id.
                ToolCall(id="toolu_01Foreign", name="quote_read", arguments={"symbol": "EURUSD"}),
            ],
        ),
        ModelMessage(role="tool", tool_call_id="call_a", content='{"bid": 2650.1}'),
        ModelMessage(role="tool", tool_call_id="toolu_01Foreign", content='{"bid": 1.05}'),
    ]
    reply = await run(server, history, [QUOTE])
    assert reply.text == "Gold is at 2650."
    assert server.body["input"] == [
        {"role": "user", "content": "What is gold doing?"},
        # An assistant's text travels as plain content (Responses refuses input_text there).
        {"role": "assistant", "content": "Hello."},
        {
            "type": "function_call",
            "call_id": "call_a",
            "name": "quote_read",
            "arguments": '{"symbol": "XAUUSD"}',
        },
        {
            "type": "function_call",
            "call_id": "toolu_01Foreign",
            "name": "quote_read",
            "arguments": '{"symbol": "EURUSD"}',
        },
        {"type": "function_call_output", "call_id": "call_a", "output": '{"bid": 2650.1}'},
        {"type": "function_call_output", "call_id": "toolu_01Foreign", "output": '{"bid": 1.05}'},
    ]
    # Nothing asks for or replays reasoning items: no output item ids, no include.
    assert "include" not in server.body
    assert all("id" not in item for item in server.body["input"])


@pytest.mark.asyncio
async def test_images_travel_as_input_image_parts_beside_the_text() -> None:
    server = Server(streamed(*started(), *text("A rising wedge."), completed()))
    image = "data:image/png;base64,cGl4ZWxz"
    messages = [
        ModelMessage(role="user", content="Read this chart.", images=[image]),
        ModelMessage(role="user", content="", images=["https://example.test/chart.png"]),
    ]
    reply = await run(server, messages)
    assert reply.text == "A rising wedge."
    assert server.body["input"] == [
        {
            "role": "user",
            "content": [
                {"type": "input_text", "text": "Read this chart."},
                {"type": "input_image", "image_url": image},
            ],
        },
        {
            "role": "user",
            "content": [{"type": "input_image", "image_url": "https://example.test/chart.png"}],
        },
    ]
    assert "instructions" not in server.body


@pytest.mark.asyncio
async def test_the_chatgpt_plan_shape_puts_tools_in_one_namespace_and_sends_no_budget() -> None:
    server = Server(
        streamed(
            *started(),
            # A namespaced call names its tool and its namespace apart.
            call("call_b", "quote_read", '{"symbol": "XAUUSD"}', namespace="lonora"),
            completed(),
        )
    )
    history = [
        *ASK,
        ModelMessage(
            role="assistant",
            content="",
            tool_calls=[ToolCall(id="call_a", name="quote_read", arguments={"symbol": "EURUSD"})],
        ),
        ModelMessage(role="tool", tool_call_id="call_a", content='{"bid": 1.05}'),
    ]
    reply = await run(server, history, [QUOTE], chatgpt_plan=True, max_output_tokens=4096)
    assert reply.tool_calls == [
        ToolCall(id="call_b", name="quote_read", arguments={"symbol": "XAUUSD"})
    ]
    body = server.body
    assert not set(body) & PLAN_UNSUPPORTED
    assert body["stream"] is True and body["store"] is False
    assert body["instructions"] == "Policy one.\n\nPolicy two."
    assert all(item.get("role") != "system" for item in body["input"])
    [namespace] = body["tools"]
    assert namespace["type"] == "namespace" and namespace["name"] == "lonora"
    assert isinstance(namespace["description"], str) and namespace["description"]
    assert [tool["name"] for tool in namespace["tools"]] == ["quote_read"]
    assert all(
        tool["type"] == "function" and tool["strict"] is False for tool in namespace["tools"]
    )
    # The replayed call names its namespace, as OpenAI's own items do.
    assert body["input"][1] == {
        "type": "function_call",
        "call_id": "call_a",
        "name": "quote_read",
        "arguments": '{"symbol": "EURUSD"}',
        "namespace": "lonora",
    }


# --- Truncation, refusals and silence --------------------------------------------------


@pytest.mark.asyncio
async def test_an_incomplete_response_never_yields_tool_calls() -> None:
    whole = Server(
        streamed(*started(), call("call_a", "trade_read", '{"operation_id": "op"}'), incomplete())
    )
    error = await failure(whole, tools=[QUOTE])
    assert error.reason is FailureReason.TRUNCATED and error.code == "model_output_truncated"
    # A call cut off mid-arguments is truncated, never read as a broken response.
    cut = Server(
        streamed(*started(), call("call_a", "trade_read", '{"operation_id": "op'), incomplete())
    )
    error = await failure(cut, tools=[QUOTE])
    assert error.reason is FailureReason.TRUNCATED
    # Any other cut-off reason is treated the same way.
    other = Server(
        streamed(*started(), call("call_a", "trade_read", "{}"), incomplete("unknown_cut"))
    )
    assert (await failure(other, tools=[QUOTE])).reason is FailureReason.TRUNCATED
    empty = Server(streamed(*started(), incomplete()))
    assert (await failure(empty, allow_empty=True)).reason is FailureReason.TRUNCATED


@pytest.mark.asyncio
async def test_cut_off_text_is_kept_and_flagged_for_the_routers_one_boost() -> None:
    server = Server(streamed(*started(), *text("Gold is"), incomplete()))
    reply = await run(server)
    assert reply.text == "Gold is" and reply.tool_calls == []
    assert reply.provider_metadata["output_truncated"] is True
    assert reply.provider_metadata["finish_reason"] == "length"


@pytest.mark.asyncio
async def test_refusals_and_content_filters_are_content_policy() -> None:
    refusal = {
        "type": "response.output_item.done",
        "output_index": 0,
        "item": {
            "type": "message",
            "id": "msg_1",
            "role": "assistant",
            "content": [{"type": "refusal", "refusal": "I can't help with that."}],
        },
    }
    refused = Server(streamed(*started(), refusal, completed()))
    error = await failure(refused, allow_empty=True)
    assert error.reason is FailureReason.CONTENT_POLICY and error.code == "model_content_blocked"
    filtered = Server(streamed(*started(), *text("Partial"), incomplete("content_filter")))
    assert (await failure(filtered)).reason is FailureReason.CONTENT_POLICY


@pytest.mark.asyncio
async def test_an_empty_completed_reply_is_silence_only_where_allowed() -> None:
    server = Server(streamed(*started(), completed()))
    reply = await run(server, allow_empty=True)
    assert reply.text == "" and reply.tool_calls == []
    error = await failure(server)
    assert error.reason is FailureReason.INVALID_RESPONSE


# --- Failures ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_a_stream_cut_before_its_terminal_event_is_interrupted_and_drops_its_calls() -> None:
    server = Server(
        streamed(*started(), *text("Reading"), call("call_a", "quote_read", '{"symbol": "XAUUSD"}'))
    )
    deltas: list[str] = []
    error = await failure(server, tools=[QUOTE], deltas=deltas)
    assert error.reason is FailureReason.CONNECTION and error.diagnostic_type == "stream_incomplete"
    assert error.code == "model_provider_unavailable"


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("event", "reason"),
    [
        # As api.openai.com answered an account without credits: the error nests.
        (
            {
                "type": "error",
                "sequence_number": 2,
                "error": {
                    "type": "insufficient_quota",
                    "code": "credit_balance_exhausted",
                    "message": "You have no credits remaining.",
                    "param": None,
                },
            },
            FailureReason.BILLING,
        ),
        # The documented flat shape.
        (
            {"type": "error", "code": "rate_limit_exceeded", "message": "Slow down", "param": None},
            FailureReason.RATE_LIMIT,
        ),
        (
            {
                "type": "response.failed",
                "response": {
                    "id": "resp_1",
                    "status": "failed",
                    "error": {"code": "server_error", "message": "The server had an error"},
                },
            },
            FailureReason.SERVER_ERROR,
        ),
        (
            {"type": "response.failed", "response": {"id": "resp_1", "status": "failed"}},
            FailureReason.SERVER_ERROR,
        ),
        # The ChatGPT plan's codes after streaming began (the specification, section 4.8).
        (
            {
                "type": "response.failed",
                "response": {
                    "status": "failed",
                    "error": {"code": "subscription_sharing_usage_limit_exceeded", "message": "x"},
                },
            },
            FailureReason.BILLING,
        ),
        (
            {
                "type": "response.failed",
                "response": {
                    "status": "failed",
                    "error": {"code": "subscription_sharing_usage_unavailable", "message": "x"},
                },
            },
            FailureReason.OVERLOADED,
        ),
    ],
)
async def test_failure_events_are_classified_and_drop_the_reply(
    event: dict[str, Any], reason: FailureReason
) -> None:
    server = Server(
        streamed(*started(), *text("Partial"), call("call_a", "quote_read", "{}"), event)
    )
    error = await failure(server, tools=[QUOTE])
    assert error.reason is reason


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "body", "headers", "reason", "code"),
    [
        (
            401,
            {"error": {"type": "invalid_request_error", "code": "invalid_api_key", "message": "x"}},
            {},
            FailureReason.AUTH,
            "model_credentials_rejected",
        ),
        (
            429,
            {"error": {"type": "requests", "code": "rate_limit_exceeded", "message": "x"}},
            {"retry-after": "3"},
            FailureReason.RATE_LIMIT,
            "model_rate_limited",
        ),
        (
            400,
            {"error": {"type": "invalid_request_error", "code": "context_length_exceeded"}},
            {},
            FailureReason.CONTEXT_OVERFLOW,
            "context_limit_exceeded",
        ),
        (
            404,
            {"error": {"type": "invalid_request_error", "code": "model_not_found", "message": "x"}},
            {},
            FailureReason.MODEL_NOT_FOUND,
            "model_endpoint_unavailable",
        ),
        (
            400,
            {"error": {"type": "invalid_request_error", "code": "invalid_value", "param": "tools"}},
            {},
            FailureReason.FORMAT_ERROR,
            "model_request_rejected",
        ),
        (
            503,
            {"error": {"message": "upstream unavailable"}},
            {},
            FailureReason.OVERLOADED,
            "model_provider_unavailable",
        ),
    ],
)
async def test_non_2xx_answers_with_json_error_bodies_are_classified(
    status: int,
    body: dict[str, Any],
    headers: dict[str, str],
    reason: FailureReason,
    code: str,
) -> None:
    server = Server(httpx.Response(status, json=body, headers=headers))
    error = await failure(server)
    assert (error.reason, error.code, error.http_status) == (reason, code, status)
    if headers:
        assert error.retry_after == 3.0


@pytest.mark.asyncio
async def test_malformed_stream_events_are_an_invalid_response() -> None:
    for broken in (
        {"type": "response.output_text.delta", "delta": 7},
        {"type": "response.output_item.done", "item": "not an item"},
        {"type": "response.completed", "response": None},
    ):
        server = Server(streamed(*started(), broken, completed()))
        assert (await failure(server)).reason is FailureReason.INVALID_RESPONSE


@pytest.mark.asyncio
async def test_discovery_reads_the_model_list_with_the_key() -> None:
    server = Server(
        httpx.Response(
            200,
            json={
                "object": "list",
                "data": [{"id": "gpt-fixture", "object": "model"}, {"object": "model"}, "x"],
            },
        )
    )
    async with httpx.AsyncClient(transport=httpx.MockTransport(server.handle)) as client:
        [model] = await OpenAIResponsesAdapter(KEY, client).discover()
    assert (model.id, model.provider, model.name) == ("gpt-fixture", "openai", "gpt-fixture")
    assert model.source == "https://api.openai.com/v1/models"
    [request] = server.seen
    assert request.method == "GET" and request.headers["authorization"] == "Bearer " + KEY
