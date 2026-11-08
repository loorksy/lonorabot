"""Owner-configured monetary risk limits and the boundary's measured risk evidence.

Every limit is optional and unset means not enforced: no money amount is ever chosen for
the owner. Amounts are in the broker account currency, which the owner names
explicitly; a currency that no longer matches the account blocks new risk instead of
being converted. Estimates use the broker's own tick economics at the stop-loss and do
not model gaps, slippage, future commission, swap or a new order's margin.
"""

from datetime import datetime
from decimal import Decimal
from typing import Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import Field, model_validator

from .domain import Contract

MONEY_FIELDS = ("max_trade_risk", "max_daily_loss", "max_open_risk", "min_free_margin")


class MonetaryRiskLimits(Contract):
    currency: str | None = Field(default=None, min_length=1, max_length=16)
    # Maximum modeled loss at the stop-loss for one new trade (or edited entry/position).
    max_trade_risk: Decimal | None = Field(default=None, gt=0)
    max_trade_risk_equity_percent: Decimal | None = Field(default=None, gt=0, le=100)
    # Realized loss of the trading day plus current floating P&L; reaching it blocks new risk.
    max_daily_loss: Decimal | None = Field(default=None, gt=0)
    # Modeled loss at the stops across open positions, pending orders and operations whose
    # broker outcome or state is not yet established, after the new request.
    max_open_risk: Decimal | None = Field(default=None, gt=0)
    max_open_risk_equity_percent: Decimal | None = Field(default=None, gt=0, le=100)
    # New entries need at least this free margin (current account free margin).
    min_free_margin: Decimal | None = Field(default=None, gt=0)
    # The trading day for max_daily_loss starts at local midnight in this IANA zone.
    trading_day_timezone: str = Field(default="UTC", min_length=1, max_length=64)

    @model_validator(mode="after")
    def coherent(self) -> "MonetaryRiskLimits":
        if self.currency is not None:
            self.currency = self.currency.strip()
            if not self.currency:
                raise ValueError("risk_currency_required")
        if any(getattr(self, name) is not None for name in MONEY_FIELDS) and not self.currency:
            raise ValueError("risk_currency_required")
        try:
            ZoneInfo(self.trading_day_timezone)
        except (ZoneInfoNotFoundError, ValueError) as error:
            raise ValueError("trading_day_timezone_invalid") from error
        return self

    @property
    def configured(self) -> bool:
        return any(
            value is not None
            for value in (
                self.max_trade_risk,
                self.max_trade_risk_equity_percent,
                self.max_daily_loss,
                self.max_open_risk,
                self.max_open_risk_equity_percent,
                self.min_free_margin,
            )
        )


class RiskItem(Contract):
    """One contributor to modeled open risk; ``risk`` None means unbounded (no stop)."""

    kind: Literal["position", "order", "operation", "candidate"]
    id: str
    symbol: str
    side: Literal["buy", "sell", "unknown"]
    volume: Decimal
    reference_price: Decimal | None = None
    stop_loss: Decimal | None = None
    risk: Decimal | None = None
    status: str | None = None


class DailyLoss(Contract):
    day_start: datetime
    timezone: str
    realized: Decimal
    unrealized: Decimal
    loss: Decimal
    deals_counted: int


class RiskAssessment(Contract):
    state: Literal["within_limits", "blocked", "not_configured", "risk_reducing"]
    reasons: list[str] = Field(default_factory=list)
    currency: str | None = None
    equity: Decimal | None = None
    free_margin: Decimal | None = None
    limits: MonetaryRiskLimits = Field(default_factory=MonetaryRiskLimits)
    trade_risk: Decimal | None = None
    trade_risk_unbounded: bool = False
    trade_risk_limit: Decimal | None = None
    open_risk: Decimal | None = None
    open_risk_unbounded: bool = False
    open_risk_limit: Decimal | None = None
    daily: DailyLoss | None = None
    items: list[RiskItem] = Field(default_factory=list[RiskItem])
    observed_at: datetime
    exclusions: tuple[str, ...] = (
        "gaps",
        "slippage",
        "future_commission",
        "swap",
        "new_order_margin",
    )
