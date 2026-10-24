"""Historical evidence belongs to its recording time, never to hindsight."""

from datetime import datetime
from typing import Literal, Self

from pydantic import Field, field_validator, model_validator

from .account import AccountState, Order, Position
from .domain import Contract
from .market import Candle, Quote
from .market_health import HealthSnapshot
from .market_intelligence import DetectorDefinition, Observation
from .relationships import MarketRelationship


class MarketViewRequest(Contract):
    """Model interpretation; optional detectors contribute observations, not a verdict."""

    bias: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    supporting_condition: DetectorDefinition | None = None


class ConditionalEntryPlan(Contract):
    """A model-authored review objective, not an order or an installed watch."""

    direction: Literal["BUY", "SELL"]
    condition: str = Field(min_length=1, max_length=1200)
    invalidation: str = Field(min_length=1, max_length=1200)
    review_instruction: str = Field(min_length=1, max_length=1200)

    @field_validator("condition", "invalidation", "review_instruction")
    @classmethod
    def meaningful_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("conditional_entry_text_required")
        return value


class MarketAssessment(Contract):
    bias: Literal["BULLISH", "BEARISH", "NEUTRAL", "INSUFFICIENT_EVIDENCE"]
    source: Literal["model_interpretation_of_broker_evidence"] = (
        "model_interpretation_of_broker_evidence"
    )
    evidence_id: str
    observed_at: datetime
    quote_observed_at: datetime | None = None
    candle_observed_at: datetime | None = None
    reason_codes: list[str] = Field(default_factory=list[str], max_length=16)
    supporting_condition: DetectorDefinition | None = None
    supporting_observation: Observation | None = None
    supporting_reason_codes: list[str] = Field(default_factory=list[str], max_length=8)
    confidence: Literal["not_calibrated"] = "not_calibrated"


class EntryReadiness(Contract):
    state: Literal[
        "CONFIRMED",
        "MODEL_SELECTED",
        "AWAITING_REASSESSMENT",
        "NOT_CONFIRMED",
        "INSUFFICIENT_EVIDENCE",
    ]
    reason_codes: list[str] = Field(default_factory=list[str], max_length=16)
    condition: DetectorDefinition | None = None
    observation: Observation | None = None


class ExecutionReadiness(Contract):
    state: Literal["BLOCKED", "REVALIDATION_REQUIRED"]
    reason_codes: list[str] = Field(default_factory=list[str], max_length=32)
    observed_at: datetime
    execution_authorized: Literal[False] = False
    remaining_checks: list[str] = Field(
        default_factory=lambda: [
            "current_financial_authorization",
            "current_instrument_and_volume",
            "current_account_exposure_and_risk",
            "final_preflight_and_execution_quality",
            "idempotency_and_reconciliation",
        ],
        max_length=8,
    )


class DecisionReadiness(Contract):
    schema_version: Literal[1, 2] = 2
    market_assessment: MarketAssessment
    entry_readiness: EntryReadiness
    execution_readiness: ExecutionReadiness


class DecisionRequest(Contract):
    account_id: str = Field(min_length=1, max_length=120)
    symbol: str = Field(min_length=1, max_length=80)
    timeframe: str = Field(min_length=1, max_length=12)
    action: Literal["BUY", "SELL", "CONDITIONAL_ENTRY", "WAIT"]
    summary: str = Field(
        min_length=1,
        max_length=1200,
        description="Concise user-visible rationale, never hidden reasoning.",
    )
    relationship_ids: list[str] = Field(default_factory=list, max_length=6)
    market_view: MarketViewRequest | None = Field(
        default=None,
        description="Model interpretation of captured evidence. Supporting detector observations are optional; never execution permission.",
    )
    entry_condition: DetectorDefinition | None = Field(
        default=None,
        description="Optional detector observation checked against captured evidence; not a prerequisite for a model-selected immediate entry.",
    )
    conditional_entry: ConditionalEntryPlan | None = Field(
        default=None,
        description="Required only for CONDITIONAL_ENTRY. Records your review objective; use an existing Task watch or timer separately to start monitoring.",
    )

    @model_validator(mode="after")
    def conditional_plan_matches_action(self) -> Self:
        if (self.action == "CONDITIONAL_ENTRY") != (self.conditional_entry is not None):
            raise ValueError("conditional_entry_action_mismatch")
        return self


class DecisionEvidence(Contract):
    schema_version: Literal[1] = 1
    id: str
    captured_at: datetime
    quote: Quote | None = None
    candles: list[Candle] = Field(default_factory=list[Candle], max_length=100)
    account: AccountState | None = None
    positions: list[Position] = Field(default_factory=list[Position], max_length=1000)
    orders: list[Order] = Field(default_factory=list[Order], max_length=1000)
    health: list[HealthSnapshot] = Field(default_factory=list[HealthSnapshot], max_length=3)
    missing_codes: list[str] = Field(default_factory=list[str], max_length=8)
    recovered_read_codes: list[str] = Field(default_factory=list[str], max_length=5)
    source: Literal["broker_adapter"] = "broker_adapter"
    relationships: list[MarketRelationship] = Field(
        default_factory=list[MarketRelationship], max_length=6
    )


class TradingDecision(Contract):
    schema_version: Literal[1, 2] = 2
    id: str
    owner_id: str
    agent_id: str
    run_id: str
    account_id: str
    symbol: str
    timeframe: str
    recorded_at: datetime
    requested_action: Literal["BUY", "SELL", "CONDITIONAL_ENTRY", "WAIT"]
    action: Literal["BUY", "SELL", "CONDITIONAL_ENTRY", "WAIT"]
    summary: str
    gate_codes: list[str]
    evidence: DecisionEvidence
    readiness: DecisionReadiness | None = None
    conditional_entry: ConditionalEntryPlan | None = None
    execution_authorized: Literal[False] = False
    logic_version: Literal["market-evidence-v1", "market-evidence-v2"] = "market-evidence-v2"


class DecisionHistory(Contract):
    account_id: str | None = None
    symbol: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class DecisionReference(Contract):
    decision_id: str


class DecisionCompare(Contract):
    earlier_id: str
    later_id: str
