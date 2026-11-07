"""Global request-admission policy, never an Agent-specific model setting."""

from typing import Any, cast

from pydantic import Field, model_validator

from .domain import Contract

DEFAULT_MAXIMUM_INPUT_TOKENS = 64000
DEFAULT_OUTPUT_TOKENS = 16384
# Output requested from a model whose maximum neither its catalog nor the family
# table reports; a provider that rejects it states its limit and is retried.
UNKNOWN_OUTPUT_TOKENS = 8192


class ModelContextPolicy(Contract):
    # Admitted input only when the selected model's context window is unknown.
    # A known window derives the budget: window - output reservation - safety.
    maximum_input_tokens: int = Field(default=DEFAULT_MAXIMUM_INPUT_TOKENS, ge=512, le=2_000_000)
    # Requested output budget, bounded per model by its documented maximum and a
    # quarter of its window; an unknown model gets at most UNKNOWN_OUTPUT_TOKENS.
    output_tokens: int = Field(default=DEFAULT_OUTPUT_TOKENS, ge=128, le=128000)
    # Minimum headroom; large windows reserve at least 2% of the window instead.
    safety_tokens: int = Field(default=1024, ge=128, le=32000)
    image_tokens: int = Field(default=8192, ge=256, le=262144)
    # Optional owner cost/latency cap on admitted input for every model.
    input_ceiling_tokens: int | None = Field(default=None, ge=512, le=10_000_000)
    # In-run compaction starts once a request would use this share of the budget.
    compaction_ratio: float = Field(default=0.75, ge=0.3, le=0.95)

    @model_validator(mode="before")
    @classmethod
    def legacy_input_cap(cls, data: Any) -> Any:
        """Keep an owner's pre-window cap: it used to bound every model.

        A stored setting or request written before ``input_ceiling_tokens``
        existed has no such key. A non-default ``maximum_input_tokens`` there was
        the owner's cap for every model, so it becomes the ceiling instead of
        silently applying only to unknown windows. Sending
        ``input_ceiling_tokens: null`` explicitly opts out.
        """
        if not isinstance(data, dict):
            return data
        values = cast(dict[str, Any], data)
        legacy = values.get("maximum_input_tokens")
        if (
            "input_ceiling_tokens" in values
            or legacy is None
            or legacy == DEFAULT_MAXIMUM_INPUT_TOKENS
        ):
            return values
        return {**values, "input_ceiling_tokens": legacy}
