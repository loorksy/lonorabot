"""Global request-admission policy, never an Agent-specific model setting."""

from pydantic import Field

from .domain import Contract


class ModelContextPolicy(Contract):
    # Admitted input only when the selected model's context window is unknown.
    # A known window derives the budget: window - output reservation - safety.
    maximum_input_tokens: int = Field(default=64000, ge=512, le=2_000_000)
    output_tokens: int = Field(default=4096, ge=128, le=128000)
    # Minimum headroom; large windows reserve at least 2% of the window instead.
    safety_tokens: int = Field(default=1024, ge=128, le=32000)
    image_tokens: int = Field(default=8192, ge=256, le=262144)
    # Optional owner cost/latency cap on admitted input for every model.
    input_ceiling_tokens: int | None = Field(default=None, ge=512, le=10_000_000)
    # In-run compaction starts once a request would use this share of the budget.
    compaction_ratio: float = Field(default=0.75, ge=0.3, le=0.95)
