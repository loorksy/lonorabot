import json
from collections.abc import Awaitable, Callable
from typing import Any

import httpx
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.usage import TokenUsage
from lonora_core.user_error import LonoraError

from .base import BaseModelAdapter


def anthropic_messages(messages: list[ModelMessage]) -> tuple[str, list[dict[str, Any]]]:
    systems: list[str] = []
    result: list[dict[str, Any]] = []
    for message in messages:
        if message.role == "system":
            systems.append(message.content)
            continue
        role = "user" if message.role in {"user", "tool"} else "assistant"
        blocks: list[dict[str, Any]] = []
        if message.role == "tool":
            blocks.append(
                {
                    "type": "tool_result",
                    "tool_use_id": message.tool_call_id,
                    "content": message.content,
                }
            )
        else:
            if message.content:
                blocks.append({"type": "text", "text": message.content})
            for image in message.images:
                if image.startswith("data:"):
                    header, data = image.split(",", 1)
                    blocks.append(
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": header.split(":", 1)[1].split(";", 1)[0],
                                "data": data,
                            },
                        }
                    )
                else:
                    blocks.append({"type": "image", "source": {"type": "url", "url": image}})
            blocks.extend(
                {"type": "tool_use", "id": call.id, "name": call.name, "input": call.arguments}
                for call in message.tool_calls
            )
        if result and result[-1]["role"] == role:
            result[-1]["content"].extend(blocks)
        else:
            result.append({"role": role, "content": blocks})
    return "\n\n".join(systems), result


def cacheable_system(system: str) -> str | list[dict[str, Any]]:
    """Cache only the immutable first-party prefix, before owner/context material.

    Native Anthropic prompt caching is optional optimization, not authorization.
    Ordinary callers retain their existing string payload; no extra provider call.
    """
    start, end = "<lonora_operating_policy>", "</lonora_operating_policy>"
    if not system.startswith(start) or end not in system:
        return system
    split = system.index(end) + len(end)
    blocks: list[dict[str, Any]] = [
        {"type": "text", "text": system[:split], "cache_control": {"type": "ephemeral"}}
    ]
    if system[split:].strip():
        blocks.append({"type": "text", "text": system[split:]})
    return blocks


class AnthropicAdapter(BaseModelAdapter):
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        super().__init__(api_key, "https://api.anthropic.com/v1", client)

    def headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}

    async def complete(
        self,
        model: str,
        messages: list[ModelMessage],
        tools: list[ToolDefinition],
        *,
        max_output_tokens: int | None = None,
        on_delta: Callable[[str], Awaitable[None]] | None = None,
    ) -> ModelReply:
        system, wire = anthropic_messages(messages)
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": max_output_tokens or 8192,
            "messages": wire,
            "system": cacheable_system(system),
        }
        if tools:
            payload["tools"] = [
                {
                    "name": tool.name,
                    "description": tool.description,
                    "input_schema": tool.parameters,
                }
                for tool in tools
            ]
        if on_delta:
            return await self.stream_complete(payload, on_delta)
        value = await self.request("POST", "/messages", headers=self.headers(), json=payload)
        try:
            blocks = value["content"]
            text = "\n".join(block["text"] for block in blocks if block.get("type") == "text")
            calls = [
                ToolCall(id=block["id"], name=block["name"], arguments=block["input"])
                for block in blocks
                if block.get("type") == "tool_use"
            ]
            usage = value.get("usage", {})
            if not text and not calls:
                raise ValueError()
            return ModelReply(
                text=text,
                tool_calls=calls,
                usage=TokenUsage(
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    cached_tokens=usage.get("cache_read_input_tokens", 0),
                ),
                provider_metadata={
                    "response_id": value.get("id"),
                    "stop_reason": value.get("stop_reason"),
                },
            )
        except (KeyError, TypeError, ValueError):
            raise LonoraError("model_response_invalid", 502) from None

    async def discover(self) -> list[ModelDescriptor]:
        descriptors: list[ModelDescriptor] = []
        params: dict[str, str | int] = {"limit": 100}
        for _ in range(10):
            value = await self.request("GET", "/models", headers=self.headers(), params=params)
            for item in value.get("data", []):
                descriptors.append(
                    ModelDescriptor(
                        id=item["id"],
                        provider="anthropic",
                        name=item.get("display_name", item["id"]),
                        source=self.base_url + "/models",
                    )
                )
            if not value.get("has_more"):
                break
            params["after_id"] = value["last_id"]
        return descriptors

    async def stream_complete(
        self, payload: dict[str, Any], on_delta: Callable[[str], Awaitable[None]]
    ) -> ModelReply:
        text = ""
        blocks: dict[int, dict[str, Any]] = {}
        usage: dict[str, Any] = {}
        response_id: str | None = None
        ended = False
        try:
            async for value in self.stream_request(
                "/messages", {**payload, "stream": True}, self.headers()
            ):
                kind = value.get("type")
                if kind == "error":
                    raise LonoraError("model_request_rejected", 502)
                if kind == "message_start":
                    usage.update(value["message"].get("usage", {}))
                    response_id = value["message"].get("id")
                elif kind == "content_block_start":
                    blocks[value["index"]] = {**value["content_block"], "partial_json": ""}
                    initial = value["content_block"].get("text", "")
                    if initial:
                        text += initial
                        await on_delta(initial)
                elif kind == "content_block_delta":
                    delta = value["delta"]
                    chunk = delta.get("text", "")
                    if chunk:
                        text += chunk
                        if len(text) > 120000:
                            raise ValueError()
                        await on_delta(chunk)
                    partial = delta.get("partial_json", "")
                    if partial:
                        blocks[value["index"]]["partial_json"] += partial
                        if len(blocks[value["index"]]["partial_json"]) > 120000:
                            raise ValueError()
                elif kind == "message_delta":
                    usage.update(value.get("usage", {}))
                elif kind == "message_stop":
                    ended = True
            calls = [
                ToolCall(
                    id=block["id"],
                    name=block["name"],
                    arguments=json.loads(block["partial_json"])
                    if block["partial_json"]
                    else block.get("input", {}),
                )
                for block in blocks.values()
                if block.get("type") == "tool_use"
            ]
            if not ended or (not text and not calls):
                raise ValueError()
            return ModelReply(
                text=text,
                tool_calls=calls,
                usage=TokenUsage(
                    input_tokens=usage.get("input_tokens", 0),
                    output_tokens=usage.get("output_tokens", 0),
                    cached_tokens=usage.get("cache_read_input_tokens", 0),
                ),
                provider_metadata={"response_id": response_id},
            )
        except (KeyError, TypeError, ValueError):
            raise LonoraError("model_response_invalid", 502) from None
