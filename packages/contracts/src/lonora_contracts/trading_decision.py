"""Historical evidence belongs to its recording time, never to hindsight."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from .account import AccountState, Order, Position
from .domain import Contract
from .market import Candle, Quote
from .market_health import HealthSnapshot
from .relationships import MarketRelationship


class DecisionRequest(Contract):
    account_id: str = Field(min_length=1, max_length=120)
    symbol: str = Field(min_length=1, max_length=80)
    timeframe: str = Field(min_length=1, max_length=12)
    action: Literal["BUY", "SELL", "WAIT"]
    summary: str = Field(
        min_length=1,
        max_length=1200,
        description="Concise user-visible rationale, never hidden reasoning.",
    )
    relationship_ids: list[str] = Field(default_factory=list, max_length=6)


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
    source: Literal["broker_adapter"] = "broker_adapter"
    relationships: list[MarketRelationship] = Field(
        default_factory=list[MarketRelationship], max_length=6
    )


class TradingDecision(Contract):
    schema_version: Literal[1] = 1
    id: str
    owner_id: str
    agent_id: str
    run_id: str
    account_id: str
    symbol: str
    timeframe: str
    recorded_at: datetime
    requested_action: Literal["BUY", "SELL", "WAIT"]
    action: Literal["BUY", "SELL", "WAIT"]
    summary: str
    gate_codes: list[str]
    evidence: DecisionEvidence
    execution_authorized: Literal[False] = False
    logic_version: Literal["market-evidence-v1"] = "market-evidence-v1"


class DecisionHistory(Contract):
    account_id: str | None = None
    symbol: str | None = None
    limit: int = Field(default=5, ge=1, le=20)


class DecisionReference(Contract):
    decision_id: str


class DecisionCompare(Contract):
    earlier_id: str
    later_id: str
