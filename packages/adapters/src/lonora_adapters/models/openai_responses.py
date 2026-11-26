"""OpenAI's Responses API (``POST /v1/responses``): OpenAI's models with an API key and,
with ``chatgpt_plan``, with the owner's ChatGPT plan (VISION Amendment 4;
docs/proposals/model-catalog-and-chatgpt-signin.md, section 3).

Every request streams and is stateless: ``store: false`` keeps nothing at OpenAI, so
the turn's whole history is sent each time. System messages become ``instructions``
(the ChatGPT plan rejects system items); an assistant's tool calls and their results
become ``function_call`` and ``function_call_output`` items.

Reasoning items are not sent back. Lonora's message history keeps an assistant's text
and tool calls only, so nothing of a reasoning item reaches the next request, and a
replayed ``function_call`` carries no output item id that would require one.

A reply that ends without ``response.completed`` never yields tool calls: an
incomplete response is a cut-off reply, and a closed stream is an interruption.
Nothing here retries; the router decides that, and a model request repeats no
external effect.
"""

import json
from collections.abc import Awaitable, Callable
from contextlib import aclosing
from typing import Any, cast

import httpx
from lonora_adapter_kit.model_errors import ModelProviderError, classify_failure
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.usage import TokenUsage

from .base import (
    BaseModelAdapter,
    chosen_silence,
    interrupted_stream,
    invalid_response,
    stopped_reply,
)

# The ChatGPT plan takes function tools only inside a namespace (its preview limits).
NAMESPACE = "lonora"
NAMESPACE_DESCRIPTION = "Lonora's tools."


def response_input(
    messages: list[ModelMessage], namespace: str | None = None
) -> tuple[str, list[dict[str, Any]]]:
    """``instructions`` from the system messages, and the ``input`` items of the rest.

    With ``namespace``, every tool is in that namespace, and a replayed call names it
    as OpenAI's own ``function_call`` items do.
    """
    systems: list[str] = []
    items: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "system":
            systems.append(message.content)
        elif message.role == "tool":
            items.append(
                {
                    "type": "function_call_output",
                    "call_id": message.tool_call_id,
                    "output": message.content,
                }
            )
        elif message.role == "user":
            content: str | list[dict[str, Any]] = message.content
            if message.images:
                content = (
                    [{"type": "input_text", "text": message.content}] if message.content else []
                )
                content += [{"type": "input_image", "image_url": image} for image in message.images]
            items.append({"role": "user", "content": content})
        else:
            if message.content:
                items.append({"role": "assistant", "content": message.content})
            items.extend(
                {
                    "type": "function_call",
                    "call_id": call.id,
                    "name": call.name,
                    "arguments": json.dumps(call.arguments),
                    **({"namespace": namespace} if namespace else {}),
                }
                for call in message.tool_calls
            )
    return "\n\n".join(systems), items


def event_error(event: dict[str, Any]) -> dict[str, Any]:
    """The error object of an ``error`` event, flat or nested, without the event's type."""
    nested = event.get("error")
    if isinstance(nested, dict):
        return cast(dict[str, Any], nested)
    return {key: value for key, value in event.items() if key != "type"}


def event_failure(error: Any) -> ModelProviderError:
    """Classify an error the stream reports after its HTTP 200.

    OpenAI reports some rejected requests (an image it cannot download or read) only
    as an ``invalid_request_error`` event; it is classified as the HTTP 400 OpenAI
    answers with for the same error, so a rejected request is not retried as an outage.
    """
    kind = cast(dict[str, Any], error).get("type") if isinstance(error, dict) else None
    return classify_failure(400 if kind == "invalid_request_error" else None, error)


class OpenAIResponsesAdapter(BaseModelAdapter):
    def __init__(
        self,
        api_key: str,
        client: httpx.AsyncClient | None = None,
        *,
        chatgpt_plan: bool = False,
    ):
        super().__init__(api_key, "https://api.openai.com/v1", client)
        # The ChatGPT plan's request limits: tools in one namespace, no output budget.
        self.chatgpt_plan = chatgpt_plan

    def request_body(
        self,
        model: str,
        messages: list[ModelMessage],
        tools: list[ToolDefinition],
        max_output_tokens: int | None,
    ) -> dict[str, Any]:
        instructions, items = response_input(messages, NAMESPACE if self.chatgpt_plan else None)
        payload: dict[str, Any] = {"model": model, "input": items, "stream": True, "store": False}
        if instructions:
            payload["instructions"] = instructions
        if tools:
            functions = [
                {
                    "type": "function",
                    "name": tool.name,
                    "description": tool.description,
                    "parameters": tool.parameters,
                    # Strict mode would make every optional argument required.
                    "strict": False,
                }
                for tool in tools
            ]
            payload["tools"] = (
                [
                    {
                        "type": "namespace",
                        "name": NAMESPACE,
                        "description": NAMESPACE_DESCRIPTION,
                        "tools": functions,
                    }
                ]
                if self.chatgpt_plan
                else functions
            )
        if max_output_tokens is not None and not self.chatgpt_plan:
            payload["max_output_tokens"] = max_output_tokens
        return payload

    async def complete(
        self,
        model: str,
        messages: list[ModelMessage],
        tools: list[ToolDefinition],
        *,
        max_output_tokens: int | None = None,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
        allow_empty: bool = False,
    ) -> ModelReply:
        payload = self.request_body(model, messages, tools, max_output_tokens)
        text = ""
        raw_calls: list[dict[str, Any]] = []
        refused = False
        ending: dict[str, Any] | None = None
        finish = "stop"
        try:
            # Closed at once on a terminal event or an error, never left to the collector.
            async with aclosing(self.stream_request("/responses", payload)) as events:
                async for event in events:
                    kind = event.get("type")
                    if kind == "error":
                        raise event_failure(event_error(event))
                    if kind == "response.failed":
                        raise event_failure(event["response"].get("error") or {})
                    if kind == "response.output_text.delta":
                        chunk = event["delta"]
                        if not isinstance(chunk, str) or len(text) + len(chunk) > 120000:
                            raise ValueError()
                        text += chunk
                        if on_delta:
                            await on_delta(chunk)
                    elif kind == "response.output_item.done":
                        item = event["item"]
                        if item.get("type") == "function_call":
                            raw_calls.append(item)
                            if len(raw_calls) > 32 or len(item["arguments"]) > 120000:
                                raise ValueError()
                        elif item.get("type") == "message":
                            refused = refused or any(
                                part.get("type") == "refusal" for part in item.get("content", [])
                            )
                    elif kind in {"response.completed", "response.incomplete"}:
                        response = event["response"]
                        if not isinstance(response, dict):
                            raise ValueError()
                        ending = cast(dict[str, Any], response)
                        if kind == "response.completed":
                            finish = "refusal" if refused else "stop"
                        else:
                            details: dict[str, Any] = ending.get("incomplete_details") or {}
                            reason = details.get("reason")
                            # Any cut-off counts as the output budget's: no call survives it.
                            finish = "content_filter" if reason == "content_filter" else "length"
                        break
            if ending is None:
                raise interrupted_stream()
            stop = stopped_reply(finish, text, bool(raw_calls))
            stop.pop("stop_reason")
            # Arguments are read only once the reply is known to be whole.
            calls = [
                ToolCall(
                    id=item["call_id"], name=item["name"], arguments=json.loads(item["arguments"])
                )
                for item in raw_calls
            ]
            if not text and not calls and not chosen_silence(allow_empty, finish):
                raise ValueError()
            usage: dict[str, Any] = ending.get("usage") or {}
            cached: dict[str, Any] = usage.get("input_tokens_details") or {}
            return ModelReply(
                text=text,
                tool_calls=calls,
                usage=TokenUsage(
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    cached_tokens=cached.get("cached_tokens", 0),
                ),
                provider_metadata={
                    "response_id": ending.get("id"),
                    "finish_reason": finish,
                    **stop,
                },
            )
        except (AttributeError, KeyError, TypeError, ValueError):
            raise invalid_response() from None

    async def discover(self) -> list[ModelDescriptor]:
        value = await self.request("GET", "/models")
        descriptors: list[ModelDescriptor] = []
        for raw in value.get("data", []):
            if not isinstance(raw, dict):
                continue
            item = cast(dict[str, Any], raw)
            if isinstance(item.get("id"), str):
                descriptors.append(
                    ModelDescriptor(
                        id=item["id"],
                        provider="openai",
                        name=item.get("name", item["id"]),
                        context_window=item.get("context_length"),
                        source=self.base_url + "/models",
                    )
                )
        return descriptors
