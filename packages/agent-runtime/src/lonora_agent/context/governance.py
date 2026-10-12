import json
from typing import Any, cast

from lonora_adapter_kit.types import ModelMessage
from lonora_core.user_error import LonoraError

MAXIMUM_CONTEXT_CHARS = 120000


def message_size(message: ModelMessage) -> int:
    """Budget textual content and tool arguments; image transport has separate limits."""
    return (
        len(message.content)
        + sum(len(call.model_dump_json()) for call in message.tool_calls)
        + len(message.tool_call_id or "")
        + 24
    )


def context_blocks(history: list[ModelMessage]) -> list[list[ModelMessage]]:
    """Keep each assistant tool request and all its results indivisible."""
    blocks: list[list[ModelMessage]] = []
    index = 0
    while index < len(history):
        message = history[index]
        if message.role == "tool":
            raise LonoraError("invalid_tool_exchange", 500)
        block = [message]
        index += 1
        if message.tool_calls:
            pending = {call.id for call in message.tool_calls}
            if message.role != "assistant" or len(pending) != len(message.tool_calls):
                raise LonoraError("invalid_tool_exchange", 500)
            while pending:
                if index >= len(history):
                    raise LonoraError("invalid_tool_exchange", 500)
                result = history[index]
                if result.role != "tool" or result.tool_call_id not in pending:
                    raise LonoraError("invalid_tool_exchange", 500)
                pending.remove(result.tool_call_id)
                block.append(result)
                index += 1
        blocks.append(block)
    return blocks


def omitted_result(content: str, budget: int) -> str:
    notice: dict[str, Any] = {
        "ok": False,
        "context_notice": "tool_result_too_large",
        "result_omitted": True,
    }
    try:
        decoded: Any = json.loads(content)
    except ValueError:
        decoded = None
    if isinstance(decoded, dict):
        result = cast(dict[str, Any], decoded)
        notice["ok"] = result.get("ok") is True
        # Omission is a presentation limit, not failure of an already executed effect.
        for key in ("status", "operation_id", "broker_reference", "code", "artifact_id", "symbol"):
            value = result.get(key)
            if isinstance(value, str) and len(value) <= 128:
                candidate = {**notice, key: value}
                if len(json.dumps(candidate, ensure_ascii=False)) <= budget:
                    notice = candidate
    return json.dumps(notice, ensure_ascii=False)


def bound_exchange(block: list[ModelMessage], budget: int) -> list[ModelMessage]:
    """Omit oversized result bodies in the working copy, preserving durable originals."""
    if len(block) < 2 or not block[0].tool_calls:
        return block
    fixed = message_size(block[0]) + sum(message_size(row) - len(row.content) for row in block[1:])
    per_result = (budget - fixed) // (len(block) - 1)
    notice = omitted_result("", per_result)
    if per_result < len(notice):
        return block
    return [block[0]] + [
        row
        if len(row.content) <= per_result
        else row.model_copy(update={"content": omitted_result(row.content, per_result)})
        for row in block[1:]
    ]


def govern_context(
    messages: list[ModelMessage], maximum_chars: int = MAXIMUM_CONTEXT_CHARS
) -> list[ModelMessage]:
    if not messages:
        raise LonoraError("empty_model_context", 500)
    system = [message for message in messages if message.role == "system"]
    blocks = context_blocks([message for message in messages if message.role != "system"])
    budget = maximum_chars - sum(message_size(message) for message in system)
    if budget < 0:
        raise LonoraError("context_limit_exceeded", 413)
    # Retain the newest user instruction even when many tool rounds follow it.
    anchor = next(
        (index for index in range(len(blocks) - 1, -1, -1) if blocks[index][0].role == "user"),
        None,
    )
    retained: dict[int, list[ModelMessage]] = {}
    if anchor is not None:
        retained[anchor] = blocks[anchor]
        budget -= sum(message_size(message) for message in blocks[anchor])
    if budget < 0:
        raise LonoraError("context_limit_exceeded", 413)
    for index in range(len(blocks) - 1, -1, -1):
        if index == anchor:
            continue
        block = blocks[index]
        size = sum(message_size(message) for message in block)
        if size > budget:
            # The newest tool exchange must remain available and protocol-complete.
            if not any(key != anchor for key in retained):
                block = bound_exchange(block, budget)
                size = sum(message_size(message) for message in block)
                if size > budget and block[0].tool_calls:
                    raise LonoraError("context_limit_exceeded", 413)
            if size > budget:
                break
        retained[index] = block
        budget -= size
    return system + [message for index in sorted(retained) for message in retained[index]]
