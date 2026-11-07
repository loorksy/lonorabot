import json
import re
from collections.abc import Callable, Sequence
from typing import Any, cast

from lonora_core.user_error import LonoraError

from lonora_adapter_kit.context_sections import is_context_message, shed_context
from lonora_adapter_kit.types import ModelMessage

# Transport guard when no admitted token limit is known. Token budgets come from
# the resolved model window; characters are only a safety net sized from them.
MAXIMUM_CONTEXT_CHARS = 120000
# Generous ceiling of characters per estimated token, so the guard never binds
# before a realistic token budget does (Arabic and JSON are denser than prose).
TRANSPORT_CHARS_PER_TOKEN = 6
OMISSION_RESERVE = 640


def transport_char_limit(input_tokens: int | None) -> int:
    """Character safety net for one request, sized from its admitted token budget."""
    if input_tokens is None or input_tokens <= 0:
        return MAXIMUM_CONTEXT_CHARS
    return max(MAXIMUM_CONTEXT_CHARS, input_tokens * TRANSPORT_CHARS_PER_TOKEN)


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
        if message.context_origin == "tool_observation":
            # Runtime observations must follow their complete producing exchange.
            raise LonoraError("invalid_tool_exchange", 500)
        if message.role == "tool":
            raise LonoraError("invalid_tool_exchange", 500)
        if message.context_origin == "runtime_context" and (
            message.role not in {"user", "system"} or message.tool_calls or message.tool_call_id
        ):
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
        # Runtime observations and notices stay bound to the complete block that
        # precedes them, so they are never retained, dropped or anchored alone.
        while index < len(history) and history[index].context_origin == "tool_observation":
            observation = history[index]
            if observation.role != "user" or observation.tool_calls or observation.tool_call_id:
                raise LonoraError("invalid_tool_exchange", 500)
            block.append(observation)
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
    results = [row for row in block[1:] if row.role == "tool"]
    if not results:
        return block
    observations = [row for row in block[1:] if row.role != "tool"]
    empty = [row.model_copy(update={"content": ""}) for row in results]
    fixed = (
        message_size(block[0])
        + sum(message_size(row) for row in empty)
        + sum(message_size(row) for row in observations)
    )
    per_result = (budget - fixed) // len(empty)
    token_limit = None
    if token_budget is not None:
        fixed_tokens = (
            token_estimate(block[0], image_tokens, count)
            + sum(token_estimate(row, image_tokens, count) for row in empty)
            + sum(token_estimate(row, image_tokens, count) for row in observations)
        )
        token_limit = (token_budget - fixed_tokens) // len(empty)
    limit = min(per_result, token_limit) if token_limit is not None else per_result

    def size(text: str) -> int:
        return max(len(text), count(text)) if token_limit is not None else len(text)

    if size(omitted_result("", limit)) > limit:
        return block
    return [block[0]] + [
        row
        if row.role != "tool"
        or (
            len(row.content) <= per_result
            and (token_limit is None or count(row.content) <= token_limit)
        )
        else row.model_copy(update={"content": omitted_result(row.content, limit, size)})
        for row in block[1:]
    ]


def guidance_label(message: ModelMessage) -> str:
    match = re.match(r"\s*<([a-z_]{1,60})[ >\n]", message.content)
    return match.group(1) if match else "first_party_guidance"


def omission_notice(messages: int, exchanges: int, *, guidance: Sequence[str] = ()) -> ModelMessage:
    """Tell the model, in place, that history or guidance was left out of this request."""
    payload: dict[str, Any] = {"source": "lonora_runtime", "reason": "context_budget"}
    if guidance:
        payload["omitted_guidance"] = list(guidance)
        payload["note"] = (
            "Optional first-party guidance was left out of this request to fit the model's "
            "context window. Server-side controls are unchanged; use tool_environment to "
            "inspect tools when needed."
        )
    else:
        payload["omitted_messages"] = messages
        payload["omitted_tool_exchanges"] = exchanges
        payload["note"] = (
            "These earlier messages were left out of this request to fit the model's "
            "context window. They still exist; do not assume they said nothing. Re-read stored "
            "results or call the tools again when exact earlier data matters."
        )
    body = json.dumps(payload, ensure_ascii=False)
    return ModelMessage(
        role="user",
        context_origin="runtime_context",
        content="<context_omitted>" + body.replace("<", "\\u003c") + "</context_omitted>",
    )


def govern_context(
    messages: list[ModelMessage],
    maximum_chars: int = MAXIMUM_CONTEXT_CHARS,
    *,
    maximum_tokens: int | None = None,
    image_tokens: int = 8192,
    count: Callable[[str], int] = lambda text: len(text.encode("utf-8")),
) -> list[ModelMessage]:
    """Admit complete exchanges under both transport and estimated token limits.

    Order of admission: first-party system messages and the newest owner request
    (mandatory), the newest exchange (bounded, never dropped), optional
    first-party guidance (each block whole), the leading context data shed
    section by section in priority order, then older history newest first. Each
    run of omitted history and any shed guidance is replaced by an explicit
    notice, so the model is told when it does not see something.
    """
    if not messages:
        raise LonoraError("empty_model_context", 500)
    # Optional first-party guidance (role system, origin runtime_context) is shed
    # whole, and reported, before a request would fail; other system text is
    # mandatory.
    system = [
        message
        for message in messages
        if message.role == "system" and message.context_origin != "runtime_context"
    ]
    optional = [
        message
        for message in messages
        if message.role == "system" and message.context_origin == "runtime_context"
    ]
    rest = [message for message in messages if message.role != "system"]
    prelude: list[ModelMessage] = []
    while rest and is_context_message(rest[0]):
        prelude.append(rest.pop(0))
    blocks = context_blocks(rest)
    budget = maximum_chars - sum(message_size(message) for message in system)
    tokens = (
        maximum_tokens - sum(token_estimate(message, image_tokens, count) for message in system)
        if maximum_tokens is not None
        else None
    )

    def exceeded() -> bool:
        return budget < 0 or (tokens is not None and tokens < 0)

    def spend(candidate: list[ModelMessage]) -> None:
        nonlocal budget, tokens
        budget -= sum(message_size(row) for row in candidate)
        if tokens is not None:
            tokens -= sum(token_estimate(row, image_tokens, count) for row in candidate)

    def fits(candidate: list[ModelMessage], reserve: int = 0) -> bool:
        return sum(message_size(row) for row in candidate) <= budget - reserve and (
            tokens is None
            or sum(token_estimate(row, image_tokens, count) for row in candidate)
            <= tokens - reserve
        )

    if exceeded():
        raise LonoraError("context_limit_exceeded", 413)
    # Retain the newest user instruction even when many tool rounds follow it.
    anchor = next(
        (
            index
            for index in range(len(blocks) - 1, -1, -1)
            if blocks[index][0].role == "user" and blocks[index][0].context_origin == "conversation"
        ),
        None,
    )
    retained: dict[int, list[ModelMessage]] = {}
    if anchor is not None:
        retained[anchor] = blocks[anchor]
        spend(blocks[anchor])
    if exceeded():
        raise LonoraError("context_limit_exceeded", 413)
    newest = len(blocks) - 1
    if newest >= 0 and newest != anchor:
        block = blocks[newest]
        if not fits(block):
            # The newest tool exchange must remain available and protocol-complete.
            block = bound_exchange(block, budget, tokens, image_tokens, count)
            if not fits(block) and block[0].tool_calls:
                raise LonoraError("context_limit_exceeded", 413)
        if fits(block):
            retained[newest] = block
            spend(block)
    admitted_optional: list[ModelMessage] = []
    shed_guidance: list[str] = []
    for message in optional:
        if fits([message], OMISSION_RESERVE):
            admitted_optional.append(message)
            spend([message])
        else:
            shed_guidance.append(guidance_label(message))
    admitted_prelude: list[ModelMessage] = []
    for message in prelude:
        # Context data is optional enrichment: shed sections, never fail the request.
        admitted = shed_context(message, lambda candidate: fits([candidate], OMISSION_RESERVE))
        if admitted is not None:
            admitted_prelude.append(admitted)
            spend([admitted])
    if newest in retained or newest == anchor:
        for index in range(newest - 1, -1, -1):
            if index == anchor:
                continue
            block = blocks[index]
            # Keep room for the notices that replace omitted runs of history;
            # admitting the oldest block means nothing is omitted at all.
            if not fits(block, 2 * OMISSION_RESERVE if index else 0):
                break
            retained[index] = block
            spend(block)
    history: list[ModelMessage] = []
    omitted_messages = omitted_exchanges = 0
    for index, block in enumerate(blocks):
        if index in retained:
            if omitted_messages:
                notice = omission_notice(omitted_messages, omitted_exchanges)
                if fits([notice]):
                    history.append(notice)
                    spend([notice])
                omitted_messages = omitted_exchanges = 0
            history.extend(retained[index])
            continue
        omitted_messages += len(block)
        omitted_exchanges += 1 if block[0].tool_calls else 0
    if omitted_messages:
        notice = omission_notice(omitted_messages, omitted_exchanges)
        if fits([notice]):
            history.append(notice)
            spend([notice])
    if shed_guidance:
        notice = omission_notice(0, 0, guidance=shed_guidance)
        if fits([notice]):
            admitted_prelude.append(notice)
    kept = {id(message) for message in admitted_optional}
    ordered_system = [
        message
        for message in messages
        if message.role == "system"
        and (message.context_origin != "runtime_context" or id(message) in kept)
    ]
    return ordered_system + admitted_prelude + history
