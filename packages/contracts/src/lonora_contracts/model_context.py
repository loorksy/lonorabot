"""Global request-admission policy, never an Agent-specific model setting."""

from pydantic import Field

from .domain import Contract


class ModelContextPolicy(Contract):
    maximum_input_tokens: int = Field(default=64000, ge=512, le=2_000_000)
    output_tokens: int = Field(default=4096, ge=128, le=128000)
    safety_tokens: int = Field(default=1024, ge=128, le=32000)
    image_tokens: int = Field(default=8192, ge=256, le=262144)
