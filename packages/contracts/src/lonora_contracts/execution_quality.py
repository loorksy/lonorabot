"""Server-owned execution policy and measured, broker-neutral evidence."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from .account import AccountState, Order, Position
from .domain import Contract
from .market import Quote
from .market_health import HealthSnapshot


class ExecutionPolicy(Contract):
    quote_max_age_seconds: int = Field(default=60, ge=1, le=60)
    account_max_age_seconds: int = Field(default=60, ge=1, le=60)


class ExposureBucket(Contract):
    symbol: str
    direction: Literal["buy", "sell", "unknown"]
    position_volume: Decimal = Decimal(0)
    pending_volume: Decimal = Decimal(0)
    positions: int = 0
    orders: int = 0
    unprotected_positions: int = 0


class ExposureSnapshot(Contract):
    account_id: str
    observed_at: datetime
    currency: str
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    buckets: list[ExposureBucket]
    # A single quote's tick values cannot value the entire cross-symbol portfolio.
    # Never add raw lots across unrelated symbols or label them monetary risk.
    notional: None = None
    monetary_stop_risk: None = None


class ExecutionSnapshot(Contract):
    account: AccountState
    positions: list[Position]
    orders: list[Order]
    quote: Quote | None = None
    observed_at: datetime


class ExecutionQuality(Contract):
    state: Literal["executable", "revalidate", "blocked", "expired", "invalidated"]
    reasons: list[str] = Field(default_factory=list)
    observed_at: datetime
    spread: Decimal | None = None
    spread_reference: Decimal | None = None
    liquidity: Literal["unknown"] = "unknown"
    health: list[HealthSnapshot] = Field(default_factory=list[HealthSnapshot])
    submission_price: Decimal | None = None
    planned_price: Decimal | None = None
    adverse_price_drift: Decimal | None = None
    quote_observed_at: datetime | None = None
    exposure: ExposureSnapshot


class PerformanceRead(Contract):
    """Live decision/outcome quality over the agent's persisted journal."""

    account_id: str | None = None
    symbol: str | None = None
    strategy_version: str | None = None
    minimum_sample: int = Field(default=20, ge=5, le=1000)
