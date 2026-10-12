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


class AnthropicAdapter(BaseModelAdapter):
    def __init__(self, api_key: str, client: httpx.AsyncClient | None = None):
        super().__init__(api_key, "https://api.anthropic.com/v1", client)

    def headers(self) -> dict[str, str]:
        return {"x-api-key": self.api_key, "anthropic-version": "2023-06-01"}

    async def complete(
        self, model: str, messages: list[ModelMessage], tools: list[ToolDefinition]
    ) -> ModelReply:
        system, wire = anthropic_messages(messages)
        payload: dict[str, Any] = {
            "model": model,
            "max_tokens": 8192,
            "messages": wire,
            "system": system,
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
