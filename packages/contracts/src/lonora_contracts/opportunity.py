"""One evolving thesis identity; evidence remains in the shared decision ledger."""

from datetime import datetime
from typing import Literal

from pydantic import Field, model_validator

from .domain import Contract

ThesisStatus = Literal[
    "forming", "confirmed", "degraded", "invalidated", "expired", "acted_on", "completed"
]


class ThesisDefinition(Contract):
    direction: Literal["BUY", "SELL", "WAIT"]
    rationale: str = Field(min_length=1, max_length=1600)
    entry_condition: str = Field(min_length=1, max_length=1200)
    invalidation_condition: str = Field(min_length=1, max_length=1200)
    target_logic: str = Field(default="", max_length=1200)
    strategy_version: str = Field(min_length=1, max_length=80)
    expires_at: datetime
    decay_at: datetime | None = None

    @model_validator(mode="after")
    def explicit_horizon(self) -> "ThesisDefinition":
        if self.expires_at.tzinfo is None or (self.decay_at and self.decay_at.tzinfo is None):
            raise ValueError("thesis_timezone_required")
        if self.decay_at and self.decay_at >= self.expires_at:
            raise ValueError("thesis_decay_must_precede_expiry")
        return self


class OpportunityCreate(Contract):
    account_id: str
    symbol: str = Field(min_length=1, max_length=80)
    timeframe: str
    setup_key: str = Field(pattern=r"^[A-Za-z0-9_.:-]{1,120}$")
    definition: ThesisDefinition
    supporting_decision_ids: list[str] = Field(default_factory=list[str], max_length=16)
    contradicting_decision_ids: list[str] = Field(default_factory=list[str], max_length=16)
    watch_id: str | None = None


class OpportunityReference(Contract):
    opportunity_id: str


class OpportunityVersion(OpportunityReference):
    version: int = Field(ge=1)


class OpportunityUpdate(OpportunityReference):
    expected_version: int = Field(ge=1)
    status: ThesisStatus
    reason_code: str = Field(pattern=r"^[a-z][a-z0-9_]{1,100}$")
    supporting_decision_ids: list[str] = Field(default_factory=list[str], max_length=16)
    contradicting_decision_ids: list[str] = Field(default_factory=list[str], max_length=16)
    definition: ThesisDefinition | None = None


class OpportunityList(Contract):
    account_id: str | None = None
    symbol: str | None = None
    limit: int = Field(default=5, ge=1, le=20)
