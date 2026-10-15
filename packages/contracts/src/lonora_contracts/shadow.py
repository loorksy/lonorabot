"""Explicit virtual execution, never a grant of live financial authority."""

from typing import Literal

from pydantic import Field

from .domain import Contract
from .trading import TradeRequest

ExecutionMode = Literal["live", "shadow"]


class AgentExecutionMode(Contract):
    execution_mode: ExecutionMode


class ShadowCommand(TradeRequest):
    decision_id: str | None = None


class ShadowRead(Contract):
    account_id: str
    symbol: str | None = None
    limit: int = Field(default=20, ge=1, le=100)


class PerformanceRead(Contract):
    execution_mode: ExecutionMode
    account_id: str | None = None
    symbol: str | None = None
    strategy_version: str | None = None
    minimum_sample: int = Field(default=20, ge=5, le=1000)
