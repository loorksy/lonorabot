"""Pure per-attempt admission; unknown model capacity stays explicitly unknown."""

import logging
from dataclasses import dataclass
from typing import Any

from lonora_adapter_kit.context import MAXIMUM_CONTEXT_CHARS, govern_context, token_estimate
from lonora_adapter_kit.tokenization import text_counter
from lonora_adapter_kit.types import ModelMessage, ToolDefinition
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_context import ModelContextPolicy
from lonora_core.user_error import LonoraError

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class PreparedContext:
    messages: list[ModelMessage]
    output_tokens: int
    diagnostics: dict[str, Any]


def prepare_context(
    messages: list[ModelMessage],
    tools: list[ToolDefinition],
    descriptor: ModelDescriptor | None,
    policy: ModelContextPolicy,
    *,
    provider: str = "openai",
    model: str = "",
) -> PreparedContext:
    estimator, count = text_counter(provider, model)
    window = descriptor.context_window if descriptor else None
    output = min(policy.output_tokens, max(1, window // 4)) if window else policy.output_tokens
    if descriptor and descriptor.maximum_output_tokens:
        output = min(output, descriptor.maximum_output_tokens)
    input_limit = policy.maximum_input_tokens
    if window:
        input_limit = min(input_limit, window - output - policy.safety_tokens)
    # Tool framing differs by provider; this bound includes both schema bytes and framing.
    schema_chars = sum(len(tool.model_dump_json()) for tool in tools)
    schema_tokens = sum(count(tool.model_dump_json()) + 64 for tool in tools)
    if input_limit <= schema_tokens or schema_chars >= MAXIMUM_CONTEXT_CHARS:
        raise LonoraError("context_limit_exceeded", 413)
    try:
        prepared = govern_context(
            messages,
            MAXIMUM_CONTEXT_CHARS - schema_chars,
            maximum_tokens=input_limit - schema_tokens,
            image_tokens=policy.image_tokens,
            count=count,
        )
    except LonoraError:
        log.warning(
            "context_admission_failed estimator=%s input_limit=%s schema_estimate=%s system_estimate=%s",
            estimator,
            input_limit,
            schema_tokens,
            sum(
                token_estimate(m, policy.image_tokens, count)
                for m in messages
                if m.role == "system"
            ),
        )
        raise
    estimate = sum(token_estimate(message, policy.image_tokens, count) for message in prepared)
    return PreparedContext(
        messages=prepared,
        output_tokens=output,
        diagnostics={
            "estimator": estimator,
            "estimated": True,
            "context_window": window,
            "capacity_source": descriptor.source if descriptor and window else "unknown",
            "input_limit": input_limit,
            "estimated_input_tokens": estimate + schema_tokens,
            "schema_estimate": schema_tokens,
            "image_allowance": policy.image_tokens,
            "reserved_output_tokens": output,
            "safety_tokens": policy.safety_tokens,
            "original_messages": len(messages),
            "retained_messages": len(prepared),
        },
    )
