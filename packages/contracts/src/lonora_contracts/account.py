from datetime import datetime
from decimal import Decimal

from .domain import Contract


class AccountState(Contract):
    id: str
    currency: str
    balance: Decimal
    equity: Decimal
    margin: Decimal
    free_margin: Decimal
    observed_at: datetime


class Position(Contract):
    id: str
    symbol: str
    side: str
    volume: Decimal
    open_price: Decimal
    profit: Decimal = Decimal(0)
    stop_loss: Decimal | None = None
    take_profit: Decimal | None = None
    operation_id: str | None = None


class Order(Contract):
    id: str
    symbol: str
    side: str
    volume: Decimal
    price: Decimal
    operation_id: str | None = None
