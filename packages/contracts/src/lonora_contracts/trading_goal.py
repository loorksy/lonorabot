from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .domain import Contract
from .market_watch import Watch
from .trading import TradeRequest


class GoalTrade(TradeRequest):
    target_step_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")

    @model_validator(mode="after")
    def validate_action(self) -> "GoalTrade":
        data = self.model_dump(exclude={"target_step_id"})
        if self.target_step_id:
            if (
                self.position_id
                or self.order_id
                or self.action
                not in {"modify_position", "close_position", "modify_order", "cancel_order"}
            ):
                raise ValueError("goal_deferred_target_invalid")
            # Validation-only marker; never persisted as a broker ID or sent to a broker.
            data["position_id" if "position" in self.action else "order_id"] = (
                "deferred-goal-target"
            )
        TradeRequest.model_validate(data)
        return self


class GoalCondition(Watch):
    target_step_id: str | None = Field(default=None, pattern=r"^[A-Za-z0-9_-]{1,64}$")

    @model_validator(mode="after")
    def validate_source(self) -> "GoalCondition":
        data = self.model_dump(exclude={"target_step_id"})
        if self.target_step_id:
            if self.kind != "position" or self.position_id:
                raise ValueError("goal_deferred_watch_invalid")
            data["position_id"] = "deferred-goal-target"
        Watch.model_validate(data)
        return self


class GoalStep(Contract):
    id: str = Field(pattern=r"^[A-Za-z0-9_-]{1,64}$")
    title: str = Field(min_length=1, max_length=300)
    kind: Literal["analysis", "watch", "review", "trade"] = "analysis"
    trade: GoalTrade | None = None
    condition: GoalCondition | None = None
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
        predecessors: set[str] = set()
        for step in self.steps:
            for target in (
                step.trade.target_step_id if step.trade else None,
                step.condition.target_step_id if step.condition else None,
            ):
                if target and target not in predecessors:
                    raise ValueError("goal_target_must_reference_prior_step")
            predecessors.add(step.id)
            if step.trade and (
                step.trade.account_id != self.account_id or step.trade.symbol != self.symbol
            ):
                raise ValueError("goal_trade_scope_mismatch")
            if (
                step.condition
                and step.condition.kind != "calendar"
                and step.condition.account_id != self.account_id
            ):
                raise ValueError("goal_watch_scope_mismatch")
            if (
                step.condition
                and step.condition.kind in {"price", "indicator"}
                and step.condition.symbol != self.symbol
            ):
                raise ValueError("goal_watch_symbol_mismatch")
        return self


class GoalPlanUpdate(Contract):
    version: int = Field(ge=1)
    steps: list[GoalStep] = Field(min_length=1, max_length=40)


class GoalControl(Contract):
    version: int = Field(ge=1)
    action: Literal["pause", "resume", "cancel"]
    autonomous: bool | None = None
    maximum_volume: Decimal | None = Field(default=None, gt=0)
    max_trade_actions: int | None = Field(default=None, ge=1, le=40)


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
