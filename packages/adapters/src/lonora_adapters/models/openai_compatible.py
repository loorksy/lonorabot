import json
from typing import Any

from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall, ToolDefinition
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_routing import ProviderId
from lonora_contracts.usage import TokenUsage
from lonora_core.user_error import LonoraError

from .base import BaseModelAdapter


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


class OpenAICompatibleAdapter(BaseModelAdapter):
    provider: ProviderId

    async def complete(
        self, model: str, messages: list[ModelMessage], tools: list[ToolDefinition]
    ) -> ModelReply:
        payload: dict[str, Any] = {
            "model": model,
            "messages": [wire_message(message) for message in messages],
            "stream": False,
        }
        if tools:
            payload["tools"] = [
                {"type": "function", "function": tool.model_dump()} for tool in tools
            ]
        value = await self.request("POST", "/chat/completions", json=payload)
        try:
            choice = value["choices"][0]
            message = choice["message"]
            calls = [
                ToolCall(
                    id=call["id"],
                    name=call["function"]["name"],
                    arguments=json.loads(call["function"]["arguments"]),
                )
                for call in message.get("tool_calls", [])
            ]
            usage = value.get("usage", {})
            text = message.get("content") or ""
            if not isinstance(text, str) or (not text and not calls):
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
                    "finish_reason": choice.get("finish_reason"),
                },
            )
        except (KeyError, IndexError, ValueError, TypeError):
            raise LonoraError("model_response_invalid", 502) from None

    async def discover(self) -> list[ModelDescriptor]:
        value = await self.request("GET", "/models")
        descriptors: list[ModelDescriptor] = []
        for item in value.get("data", []):
            if not isinstance(item, dict) or not isinstance(item.get("id"), str):
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
            descriptors.append(
                ModelDescriptor(
                    id=item["id"],
                    provider=self.provider,
                    name=item.get("name", item["id"]),
                    capabilities=capabilities,
                    verified=verified,
                    context_window=item.get("context_length"),
                    source=self.base_url + "/models",
                )
            )
        return descriptors
