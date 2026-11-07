"""Pure per-attempt admission sized from the resolved model's context window."""

import logging
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from lonora_adapter_kit.context import govern_context, token_estimate, transport_char_limit
from lonora_adapter_kit.tokenization import text_counter
from lonora_adapter_kit.types import ModelMessage, ToolDefinition
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_context import UNKNOWN_OUTPUT_TOKENS, ModelContextPolicy
from lonora_core.user_error import LonoraError

from .model_windows import FAMILY_SOURCE, family_output, family_window

# Admission never shrinks below this share of the derived input budget, however
# often a provider rejects a request as too long.
MINIMUM_INPUT_SCALE = 0.3

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class ContextLimits:
    """The admitted request size for one model, derived from its window."""

    window: int | None
    capacity_source: str
    output_tokens: int
    safety_tokens: int
    input_tokens: int
    transport_chars: int
    image_tokens: int
    compaction_tokens: int
    estimator: str
    count: Callable[[str], int]


def output_ceiling(descriptor: ModelDescriptor | None, model: str = "") -> int | None:
    """The model's documented maximum output: catalog first, then family table."""
    if descriptor and descriptor.maximum_output_tokens:
        return descriptor.maximum_output_tokens
    return family_output(model or (descriptor.id if descriptor else ""))


def context_limits(
    descriptor: ModelDescriptor | None,
    policy: ModelContextPolicy,
    *,
    provider: str = "openai",
    model: str = "",
    input_scale: float = 1.0,
) -> ContextLimits:
    """Window minus output reservation and safety margin; unknown stays explicit.

    The catalog window wins; a conservative family table fills the gap for
    providers whose model listing has none; otherwise the policy's
    ``maximum_input_tokens`` applies and capacity is reported as unknown. The
    output reservation is the policy's budget bounded by the model's documented
    maximum (``UNKNOWN_OUTPUT_TOKENS`` when none is known) and a quarter of the
    window. ``input_scale`` below 1 tightens admission after a provider proved
    an estimate too optimistic by rejecting a request as too long.
    """
    estimator, count = text_counter(provider, model)
    window = descriptor.context_window if descriptor else None
    source = descriptor.source if descriptor and window else "unknown"
    if window is None:
        window = family_window(model or (descriptor.id if descriptor else ""))
        source = FAMILY_SOURCE if window else "unknown"
    output = min(policy.output_tokens, max(1, window // 4)) if window else policy.output_tokens
    output = min(output, output_ceiling(descriptor, model) or UNKNOWN_OUTPUT_TOKENS)
    safety = max(policy.safety_tokens, window // 50) if window else policy.safety_tokens
    input_tokens = window - output - safety if window else policy.maximum_input_tokens
    if policy.input_ceiling_tokens is not None:
        input_tokens = min(input_tokens, policy.input_ceiling_tokens)
    scale = min(1.0, max(MINIMUM_INPUT_SCALE, input_scale))
    if scale < 1.0:
        input_tokens = int(input_tokens * scale)
    return ContextLimits(
        window=window,
        capacity_source=source,
        output_tokens=output,
        safety_tokens=safety,
        input_tokens=input_tokens,
        transport_chars=transport_char_limit(input_tokens),
        image_tokens=policy.image_tokens,
        compaction_tokens=int(max(input_tokens, 0) * policy.compaction_ratio),
        estimator=estimator,
        count=count,
    )


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
    input_scale: float = 1.0,
) -> PreparedContext:
    limits = context_limits(
        descriptor, policy, provider=provider, model=model, input_scale=input_scale
    )
    count = limits.count
    # Tool framing differs by provider; this bound includes both schema bytes and framing.
    schema_chars = sum(len(tool.model_dump_json()) for tool in tools)
    schema_tokens = sum(count(tool.model_dump_json()) + 64 for tool in tools)
    if limits.input_tokens <= schema_tokens or schema_chars >= limits.transport_chars:
        raise LonoraError("context_limit_exceeded", 413)
    try:
        prepared = govern_context(
            messages,
            limits.transport_chars - schema_chars,
            maximum_tokens=limits.input_tokens - schema_tokens,
            image_tokens=policy.image_tokens,
            count=count,
        )
    except LonoraError:
        log.warning(
            "context_admission_failed estimator=%s input_limit=%s schema_estimate=%s system_estimate=%s",
            limits.estimator,
            limits.input_tokens,
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
        output_tokens=limits.output_tokens,
        diagnostics={
            "estimator": limits.estimator,
            "estimated": True,
            "context_window": limits.window,
            "capacity_source": limits.capacity_source,
            "input_limit": limits.input_tokens,
            "transport_char_limit": limits.transport_chars,
            "estimated_input_tokens": estimate + schema_tokens,
            "schema_estimate": schema_tokens,
            "image_allowance": policy.image_tokens,
            "reserved_output_tokens": limits.output_tokens,
            "safety_tokens": limits.safety_tokens,
            "input_scale": min(1.0, max(MINIMUM_INPUT_SCALE, input_scale)),
            "original_messages": len(messages),
            "retained_messages": len(prepared),
            "omission_notices": sum(
                1 for message in prepared if message.content.startswith("<context_omitted>")
            ),
        },
    )
