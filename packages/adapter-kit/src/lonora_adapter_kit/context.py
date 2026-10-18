import json
from collections.abc import Callable
from typing import Any, cast

from lonora_core.user_error import LonoraError

from lonora_adapter_kit.types import ModelMessage

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


def omitted_result(content: str, budget: int, size: Callable[[str], int] = len) -> str:
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
        if isinstance(result.get("result_persisted"), bool):
            candidate = {**notice, "result_persisted": result["result_persisted"]}
            if size(json.dumps(candidate, ensure_ascii=False)) <= budget:
                notice = candidate
        # Omission is a presentation limit, not failure of an already executed effect.
        for key in (
            "status",
            "operation_id",
            "broker_reference",
            "code",
            "artifact_id",
            "symbol",
            "result_ref",
            "result_read_tool",
            "result_format",
            "result_retention",
            "result_storage_error",
        ):
            value = result.get(key)
            if isinstance(value, str) and len(value) <= 128:
                candidate = {**notice, key: value}
                if size(json.dumps(candidate, ensure_ascii=False)) <= budget:
                    notice = candidate
    return json.dumps(notice, ensure_ascii=False)


def token_estimate(
    message: ModelMessage,
    image_tokens: int = 8192,
    count: Callable[[str], int] = lambda text: len(text.encode("utf-8")),
) -> int:
    """Include framing, tool payloads and an explicit configurable image estimate.

    Counts remain estimates, not measured provider usage. No remote data is fetched.
    """
    return (
        count(message.content)
        + sum(count(call.model_dump_json()) for call in message.tool_calls)
        + count(message.tool_call_id or "")
        + len(message.images) * image_tokens
        + 32
    )


def bound_exchange(
    block: list[ModelMessage],
    budget: int,
    token_budget: int | None = None,
    image_tokens: int = 8192,
    count: Callable[[str], int] = lambda text: len(text.encode("utf-8")),
) -> list[ModelMessage]:
    """Omit result bodies only in the working copy, preserving effect identities."""
    if len(block) < 2 or not block[0].tool_calls:
        return block
    empty = [row.model_copy(update={"content": ""}) for row in block[1:]]
    fixed = message_size(block[0]) + sum(message_size(row) for row in empty)
    per_result = (budget - fixed) // len(empty)
    token_limit = None
    if token_budget is not None:
        fixed_tokens = token_estimate(block[0], image_tokens, count) + sum(
            token_estimate(row, image_tokens, count) for row in empty
        )
        token_limit = (token_budget - fixed_tokens) // len(empty)
    limit = min(per_result, token_limit) if token_limit is not None else per_result

    def size(text: str) -> int:
        return max(len(text), count(text)) if token_limit is not None else len(text)

    if size(omitted_result("", limit)) > limit:
        return block
    return [block[0]] + [
        row
        if len(row.content) <= per_result
        and (token_limit is None or count(row.content) <= token_limit)
        else row.model_copy(update={"content": omitted_result(row.content, limit, size)})
        for row in block[1:]
    ]


def govern_context(
    messages: list[ModelMessage],
    maximum_chars: int = MAXIMUM_CONTEXT_CHARS,
    *,
    maximum_tokens: int | None = None,
    image_tokens: int = 8192,
    count: Callable[[str], int] = lambda text: len(text.encode("utf-8")),
) -> list[ModelMessage]:
    """Admit complete exchanges under both transport and estimated token limits."""
    if not messages:
        raise LonoraError("empty_model_context", 500)
    system = [message for message in messages if message.role == "system"]
    blocks = context_blocks([message for message in messages if message.role != "system"])
    budget = maximum_chars - sum(message_size(message) for message in system)
    tokens = (
        maximum_tokens - sum(token_estimate(message, image_tokens, count) for message in system)
        if maximum_tokens is not None
        else None
    )

    def exceeded() -> bool:
        return budget < 0 or (tokens is not None and tokens < 0)

    if exceeded():
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
        if tokens is not None:
            tokens -= sum(
                token_estimate(message, image_tokens, count) for message in blocks[anchor]
            )
    if exceeded():
        raise LonoraError("context_limit_exceeded", 413)

    def fits(candidate: list[ModelMessage]) -> bool:
        return sum(message_size(row) for row in candidate) <= budget and (
            tokens is None
            or sum(token_estimate(row, image_tokens, count) for row in candidate) <= tokens
        )

    for index in range(len(blocks) - 1, -1, -1):
        if index == anchor:
            continue
        block = blocks[index]
        if not fits(block):
            # The newest tool exchange must remain available and protocol-complete.
            if not any(key != anchor for key in retained):
                block = bound_exchange(block, budget, tokens, image_tokens, count)
                if not fits(block) and block[0].tool_calls:
                    raise LonoraError("context_limit_exceeded", 413)
            if not fits(block):
                break
        retained[index] = block
        budget -= sum(message_size(message) for message in block)
        if tokens is not None:
            tokens -= sum(token_estimate(message, image_tokens, count) for message in block)
    return system + [message for index in sorted(retained) for message in retained[index]]
