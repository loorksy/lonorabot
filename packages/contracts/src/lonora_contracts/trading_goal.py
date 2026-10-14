from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .domain import Contract
from .market_watch import Watch
from .trading import TradeRequest


class GoalStep(Contract):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    title: str = Field(min_length=1, max_length=300)
    kind: Literal["analysis", "watch", "review", "trade"] = "analysis"
    trade: TradeRequest | None = None
    condition: Watch | None = None
    review_interval_seconds: int | None = Field(default=None, ge=60, le=31536000)

    @model_validator(mode="after")
    def validate_step(self) -> "GoalStep":
        if (self.kind == "trade") != (self.trade is not None):
            raise ValueError("goal_trade_step_requires_declared_trade")
        if self.kind == "watch" and self.condition is None:
            raise ValueError("goal_watch_condition_required")
        return self


class GoalCreate(Contract):
    agent_id: str
    thread_id: str
    title: str = Field(min_length=1, max_length=160)
    objective: str = Field(min_length=1, max_length=8000)
    account_id: str = Field(min_length=1, max_length=120)
    symbol: str = Field(min_length=1, max_length=80)
    steps: list[GoalStep] = Field(min_length=1, max_length=40)
    autonomous: bool = False
    maximum_volume: Decimal | None = Field(default=None, gt=0)
    max_trade_actions: int = Field(default=1, ge=1, le=40)

    @model_validator(mode="after")
    def validate_scope(self) -> "GoalCreate":
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError("goal_step_id_duplicate")
        for step in self.steps:
            if step.trade and (step.trade.account_id != self.account_id or step.trade.symbol != self.symbol):
                raise ValueError("goal_trade_scope_mismatch")
            if step.condition and step.condition.kind != "calendar" and step.condition.account_id != self.account_id:
                raise ValueError("goal_watch_scope_mismatch")
            if step.condition and step.condition.kind in {"price", "indicator"} and step.condition.symbol != self.symbol:
                raise ValueError("goal_watch_symbol_mismatch")
        return self


class GoalPlanUpdate(Contract):
    version: int = Field(ge=1)
    steps: list[GoalStep] = Field(min_length=1, max_length=40)


class GoalControl(Contract):
    version: int = Field(ge=1)
    action: Literal["pause", "resume", "cancel"]
    autonomous: bool | None = None


class GoalWake(Contract):
    step_id: str | None = None


class GoalReference(Contract):
    goal_id: str
    step_id: str | None = None


class GoalStepNote(GoalReference):
    note: str = Field(min_length=1, max_length=8000)
    evidence_refs: list[str] = Field(default_factory=list[str], max_length=30)


class GoalExecution(Contract):
    goal_id: str
    step_id: str
    decision_id: str
    attempt: int
    plan_version: int
