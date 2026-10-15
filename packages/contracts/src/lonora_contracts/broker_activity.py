"""Bounded broker-authoritative recovery state and external activity facts."""

from datetime import datetime
from typing import Literal

from pydantic import Field

from .account import AccountState, Order, Position
from .domain import Contract

BrokerRecoveryStatus = Literal["connected", "degraded", "disconnected", "recovering", "reconciling"]


class BrokerActivity(Contract):
    id: str
    account_id: str
    symbol: str
    ticket: str
    resource: Literal["position", "order"]
    change: Literal["discovered", "opened", "closed", "modified", "partial_close", "cancelled"]
    origin: Literal["lonora", "external"]
    observed_at: datetime
    previous: Position | Order | None = None
    current: Position | Order | None = None
    authority: Literal["observe_only"] = "observe_only"
    owner_rationale: None = None


class BrokerRecoverySnapshot(Contract):
    status: BrokerRecoveryStatus
    reason_code: str
    since: datetime
    observed_at: datetime
    last_success_at: datetime | None = None
    reconciled_at: datetime | None = None
    revision: int = Field(default=0, ge=0)
    external_revision: int = Field(default=0, ge=0)
    unresolved_operations: list[str] = Field(default_factory=list[str], max_length=1000)
    account: AccountState | None = None
    positions: list[Position] = Field(default_factory=list[Position], max_length=1000)
    orders: list[Order] = Field(default_factory=list[Order], max_length=1000)
