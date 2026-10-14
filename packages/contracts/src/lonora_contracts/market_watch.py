from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .domain import Contract


class Watch(Contract):
    goal_id: str | None = None
    step_id: str | None = None
    goal_plan_version: int | None = Field(default=None, ge=1)
    kind: Literal["price", "indicator", "position", "account", "calendar"] = "price"
    account_id: str = ""
    symbol: str = ""
    condition: Literal[
        "above", "below", "cross_above", "cross_below", "changed", "closed", "opened", "due"
    ]
    level: Decimal = Decimal(0)
    prompt: str = Field(min_length=1, max_length=8000)
    enabled: bool = True
    cooldown_seconds: int = Field(default=300, ge=30)
    interval_seconds: int = Field(default=30, ge=5)
    timeframe: str = "1h"
    indicator: Literal["sma", "ema", "rsi", "macd", "atr", "bollinger"] = "rsi"
    period: int = Field(default=14, ge=2, le=500)
    series: str = "value"
    metric: Literal["balance", "equity", "margin", "free_margin", "profit", "volume"] = "equity"
    position_id: str | None = None
    integration_id: str | None = None
    currency: str | None = None
    event_id: str | None = None

    @model_validator(mode="after")
    def validate_source(self) -> "Watch":
        if bool(self.goal_id) != bool(self.step_id):
            raise ValueError("goal_and_step_required_together")
        if not self.level.is_finite():
            raise ValueError("invalid_watch_level")
        if self.kind != "calendar" and not self.account_id:
            raise ValueError("watch_account_required")
        if self.kind in {"price", "indicator"} and not self.symbol:
            raise ValueError("watch_symbol_required")
        if self.kind == "price" and self.level <= 0:
            raise ValueError("watch_price_required")
        if self.kind == "calendar" and (not self.integration_id or self.condition != "due"):
            raise ValueError("watch_calendar_required")
        if self.kind == "position" and not self.position_id:
            raise ValueError("watch_position_required")
        if self.kind == "account" and self.metric not in {
            "balance",
            "equity",
            "margin",
            "free_margin",
        }:
            raise ValueError("watch_account_metric_invalid")
        if (
            self.kind == "position"
            and self.metric not in {"profit", "volume"}
            and self.condition not in {"closed", "opened"}
        ):
            raise ValueError("watch_position_metric_invalid")
        return self
