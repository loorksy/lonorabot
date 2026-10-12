from decimal import Decimal
from typing import Any, Literal

from pydantic import Field, model_validator

from .domain import Contract, new_id


class TradingControl(Contract):
    enabled: bool = False
    emergency_stop: bool = False


class TradeRequest(Contract):
    account_id: str
    operation_id: str = Field(default_factory=new_id, max_length=80)
    action: Literal[
        "buy",
        "sell",
        "buy_limit",
        "sell_limit",
        "buy_stop",
        "sell_stop",
        "close_position",
        "modify_position",
        "cancel_order",
        "modify_order",
    ]
    symbol: str = Field(min_length=1, max_length=80)
    volume: Decimal | None = Field(default=None, gt=0)
    price: Decimal | None = Field(default=None, gt=0)
    stop_loss: Decimal | None = Field(default=None, gt=0)
    take_profit: Decimal | None = Field(default=None, gt=0)
    position_id: str | None = None
    order_id: str | None = None

    @model_validator(mode="after")
    def validate_action(self) -> "TradeRequest":
        if (
            self.action in {"buy", "sell", "buy_limit", "sell_limit", "buy_stop", "sell_stop"}
            and self.volume is None
        ):
            raise ValueError("volume_required")
        if (
            self.action in {"buy_limit", "sell_limit", "buy_stop", "sell_stop"}
            and self.price is None
        ):
            raise ValueError("price_required")
        if "position" in self.action and not self.position_id:
            raise ValueError("position_required")
        if "order" in self.action and not self.order_id:
            raise ValueError("order_required")
        return self


class TradeResult(Contract):
    operation_id: str
    status: Literal["confirmed", "failed", "ambiguous", "submitted"]
    broker_id: str | None = None
    code: str | None = None
    details: dict[str, Any] = Field(default_factory=dict)
