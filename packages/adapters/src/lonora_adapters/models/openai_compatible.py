import json
from collections.abc import Awaitable, Callable
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_routing import ProviderId
from lonora_contracts.usage import TokenUsage

from .base import (
    BaseModelAdapter,
    interrupted_stream,
    invalid_response,
    stopped_reply,
    stream_error,
)


def wire_message(message: ModelMessage) -> dict[str, Any]:
    content: str | list[dict[str, Any]] = message.content
    if message.images:
        content = [{"type": "text", "text": message.content}] + [
            {"type": "image_url", "image_url": {"url": image}} for image in message.images
        ]
    result: dict[str, Any] = {"role": message.role, "content": content}
    if message.tool_call_id:
        result["tool_call_id"] = message.tool_call_id
    if message.tool_calls:
        result["tool_calls"] = [
            {
                "id": call.id,
                "type": "function",
                "function": {"name": call.name, "arguments": json.dumps(call.arguments)},
            }
            for call in message.tool_calls
        ]
    return result


def _parts(content: str | list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [{"type": "text", "text": content}] if isinstance(content, str) else content


def wire_messages(messages: list[ModelMessage]) -> list[dict[str, Any]]:
    """Wire messages with adjacent plain user turns coalesced into one.

    Context data, a kept request with its compaction summary, or runtime notices
    can put several user turns in a row. Some OpenAI-compatible endpoints reject
    successive user messages, so they are joined in order, as
    ``anthropic_messages`` merges same-role turns. Tool results, assistant turns
    and system messages are forwarded unchanged.
    """
    result: list[dict[str, Any]] = []
    for message in messages:
        wired = wire_message(message)
        previous = result[-1] if result else None
        if previous is None or message.role != "user" or previous["role"] != "user":
            result.append(wired)
            continue
        if isinstance(previous["content"], str) and isinstance(wired["content"], str):
            previous["content"] = previous["content"] + "\n\n" + wired["content"]
        else:
            previous["content"] = _parts(previous["content"]) + _parts(wired["content"])
    return result


class OpenAICompatibleAdapter(BaseModelAdapter):
    provider: ProviderId

    async def complete(
        self,
        model: str,
        messages: list[ModelMessage],
        tools: list[ToolDefinition],
        *,
        max_output_tokens: int | None = None,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> ModelReply:
        payload: dict[str, Any] = {
            "model": model,
            "messages": wire_messages(messages),
            "stream": False,
        }
        if max_output_tokens is not None:
            output_field = "max_completion_tokens" if self.provider == "openai" else "max_tokens"
            payload[output_field] = max_output_tokens
        if tools:
            payload["tools"] = [
                {"type": "function", "function": tool.model_dump()} for tool in tools
            ]
        if on_delta:
            return await self.stream_complete(payload, on_delta)
        value = await self.request("POST", "/chat/completions", json=payload)
        if value.get("error"):
            # Some compatible gateways answer 200 with an error object.
            raise stream_error(value)
        try:
            choice = value["choices"][0]
            message = choice["message"]
            text = message.get("content") or ""
            if not isinstance(text, str):
                raise ValueError()
            raw_calls: list[Any] = message.get("tool_calls") or []
            stop = stopped_reply(choice.get("finish_reason"), text, bool(raw_calls))
            calls = [
                ToolCall(
                    id=call["id"],
                    name=call["function"]["name"],
                    arguments=json.loads(call["function"]["arguments"]),
                )
                for call in raw_calls
            ]
            usage = value.get("usage", {})
            if not text and not calls:
                raise ValueError()
            return ModelReply(
                text=text,
                tool_calls=calls,
                usage=TokenUsage(
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                    cached_tokens=usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
                ),
                provider_metadata={
                    "response_id": value.get("id"),
                    "finish_reason": stop.pop("stop_reason"),
                    **stop,
                },
            )
        except (KeyError, IndexError, ValueError, TypeError):
            raise invalid_response() from None

    async def discover(self) -> list[ModelDescriptor]:
        value = await self.request("GET", "/models")
        descriptors: list[ModelDescriptor] = []
        for raw in value.get("data", []):
            if not isinstance(raw, dict):
                continue
            item = cast(dict[str, Any], raw)
            if not isinstance(item.get("id"), str):
                continue
            capabilities: list[str] = []
            verified = False
            if self.provider == "openrouter":
                architecture = item.get("architecture", {})
                inputs = architecture.get("input_modalities", [])
                outputs = architecture.get("output_modalities", [])
                parameters = item.get("supported_parameters", [])
                if "text" in inputs and "text" in outputs:
                    capabilities.append("text")
                if "image" in inputs:
                    capabilities.append("vision")
                if "tools" in parameters:
                    capabilities.append("tools")
                if "reasoning" in parameters:
                    capabilities.append("reasoning")
                verified = bool(inputs or outputs or parameters)
            raw_top: Any = item.get("top_provider")
            top: dict[str, Any] = cast(dict[str, Any], raw_top) if isinstance(raw_top, dict) else {}
            descriptors.append(
                ModelDescriptor(
                    id=item["id"],
                    provider=self.provider,
                    name=item.get("name", item["id"]),
                    capabilities=capabilities,
                    verified=verified,
                    context_window=item.get("context_length"),
                    maximum_output_tokens=top.get("max_completion_tokens")
                    if self.provider == "openrouter"
                    else None,
                    source=self.base_url + "/models",
                )
            )
        return descriptors

    async def stream_complete(
        self, payload: dict[str, Any], on_delta: Callable[[str], Awaitable[None]]
    ) -> ModelReply:
        payload = {**payload, "stream": True, "stream_options": {"include_usage": True}}
        text = ""
        calls: dict[int, dict[str, Any]] = {}
        usage: dict[str, Any] = {}
        metadata: dict[str, Any] = {}
        ended = False
        try:
            async for value in self.stream_request("/chat/completions", payload):
                if value.get("error"):
                    raise stream_error(value)
                if value.get("id"):
                    metadata["response_id"] = value["id"]
                if value.get("usage"):
                    usage = value["usage"]
                for choice in value.get("choices", []):
                    if choice.get("finish_reason"):
                        ended = True
                        metadata["finish_reason"] = choice["finish_reason"]
                    delta = choice.get("delta", {})
                    chunk = delta.get("content") or ""
                    if chunk:
                        if not isinstance(chunk, str) or len(text) + len(chunk) > 120000:
                            raise ValueError()
                        text += chunk
                        await on_delta(chunk)
                    for fragment in delta.get("tool_calls", []):
                        call = calls.setdefault(
                            int(fragment["index"]), {"id": "", "name": "", "arguments": ""}
                        )
                        call["id"] += fragment.get("id", "")
                        function = fragment.get("function", {})
                        call["name"] += function.get("name", "")
                        call["arguments"] += function.get("arguments", "")
                        if len(call["arguments"]) > 120000 or len(calls) > 32:
                            raise ValueError()
            if not ended:
                raise interrupted_stream()
            stop = stopped_reply(metadata.get("finish_reason"), text, bool(calls))
            stop.pop("stop_reason")
            if not text and not calls:
                raise ValueError()
            return ModelReply(
                text=text,
                tool_calls=[
                    ToolCall(
                        id=call["id"], name=call["name"], arguments=json.loads(call["arguments"])
                    )
                    for _, call in sorted(calls.items())
                ],
                usage=TokenUsage(
                    input_tokens=usage.get("prompt_tokens", 0),
                    output_tokens=usage.get("completion_tokens", 0),
                    cached_tokens=usage.get("prompt_tokens_details", {}).get("cached_tokens", 0),
                ),
                provider_metadata={**metadata, **stop},
            )
        except (KeyError, TypeError, ValueError):
            raise invalid_response() from None
