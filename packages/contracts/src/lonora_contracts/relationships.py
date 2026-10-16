"""Measured relationship evidence never grants financial authority."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .domain import Contract
from .market_health import HealthSnapshot


class RelationshipRequest(Contract):
    account_id: str = Field(min_length=1, max_length=120)
    symbols: list[str] = Field(min_length=2, max_length=2)
    timeframe: str = Field(min_length=1, max_length=12)
    window: int = Field(default=30, ge=10, le=240)

    @model_validator(mode="after")
    def distinct_symbols(self) -> "RelationshipRequest":
        if any(not value or len(value) > 80 for value in self.symbols):
            raise ValueError("invalid_relationship_symbol")
        if self.symbols[0].casefold() == self.symbols[1].casefold():
            raise ValueError("relationship_requires_distinct_symbols")
        return self


class RelationshipReference(Contract):
    relationship_id: str


class RelationshipSample(Contract):
    start: datetime
    end: datetime
    left_return: float = Field(allow_inf_nan=False)
    right_return: float = Field(allow_inf_nan=False)


class MarketRelationship(Contract):
    id: str
    owner_id: str
    agent_id: str
    account_id: str
    symbols: list[str] = Field(min_length=2, max_length=2)
    timeframe: str
    window: int
    observed_at: datetime
    valid_until: datetime | None = None
    available: bool = False
    state: Literal["stable", "weakening", "breaking", "inverted", "unreliable", "unavailable"] = (
        "unavailable"
    )
    correlation: float | None = None
    baseline_correlation: float | None = None
    correlation_delta: float | None = None
    sample_count: int = 0
    baseline_count: int = 0
    alignment_ratio: float = 0
    samples: list[RelationshipSample] = Field(
        default_factory=list[RelationshipSample], max_length=480
    )
    health: list[HealthSnapshot] = Field(default_factory=list[HealthSnapshot], max_length=2)
    reason_codes: list[str] = Field(default_factory=list, max_length=8)
    source_hashes: list[str] = Field(default_factory=list, max_length=2)
    execution_authorized: Literal[False] = False
    causal_claim: Literal[False] = False
    methodology: Literal["aligned-closed-log-returns-pearson-v1"] = (
        "aligned-closed-log-returns-pearson-v1"
    )
