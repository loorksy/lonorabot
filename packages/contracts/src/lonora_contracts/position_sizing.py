"""Read-only broker-unit sizing; an estimate cannot authorize execution."""

from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field

from .domain import Contract
from .market import Instrument


class PositionSizingRequest(Contract):
    account_id: str = Field(min_length=1, max_length=80)
    symbol: str = Field(min_length=1, max_length=80)
    side: Literal["buy", "sell"]
    risk_budget: Decimal = Field(gt=0)
    currency: str = Field(min_length=1, max_length=80)
    stop_loss: Decimal = Field(gt=0)


class PositionSizingResult(Contract):
    account_id: str
    currency: str
    symbol: str
    side: Literal["buy", "sell"]
    risk_budget: Decimal = Field(gt=0)
    entry: Decimal = Field(gt=0)
    stop_loss: Decimal = Field(gt=0)
    volume: Decimal = Field(gt=0)
    modeled_stop_loss: Decimal = Field(gt=0)
    per_lot_stop_loss: Decimal = Field(gt=0)
    tick_size: Decimal = Field(gt=0)
    loss_tick_value: Decimal = Field(gt=0)
    tick_value_basis: Literal["account_currency_per_lot"] = "account_currency_per_lot"
    quote_at: datetime
    account_at: datetime
    observed_at: datetime
    source: str
    instrument: Instrument
    execution_authorized: Literal[False] = False
    exclusions: tuple[str, ...] = ("gaps", "slippage", "commission", "swap", "margin_validation")
