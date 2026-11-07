from datetime import datetime
from decimal import Decimal
from typing import Literal

from pydantic import Field, model_validator

from .domain import Contract


class Instrument(Contract):
    symbol: str = Field(min_length=1, max_length=80)
    description: str = ""
    digits: int = Field(ge=0, le=12)
    tick_size: Decimal = Field(gt=0)
    volume_min: Decimal = Field(gt=0)
    volume_max: Decimal = Field(gt=0)
    volume_step: Decimal = Field(gt=0)
    stops_level: int = Field(default=0, ge=0)
    point_size: Decimal | None = Field(default=None, gt=0)
    contract_size: Decimal | None = Field(default=None, gt=0)
    base_currency: str | None = Field(default=None, min_length=1, max_length=80)
    profit_currency: str | None = Field(default=None, min_length=1, max_length=80)


class Quote(Contract):
    symbol: str
    bid: Decimal = Field(gt=0)
    ask: Decimal = Field(gt=0)
    observed_at: datetime
    source: str
    # MetaApi uses these values directly in account P&L for one lot and one tick.
    # The exchange rate below is separate metadata, never an extra tick multiplier.
    profit_tick_value: Decimal | None = Field(default=None, gt=0)
    loss_tick_value: Decimal | None = Field(default=None, gt=0)
    tick_value_basis: Literal["account_currency_per_lot"] | None = None
    account_currency_exchange_rate: Decimal | None = Field(default=None, gt=0)

    @model_validator(mode="after")
    def validate_spread(self) -> "Quote":
        if self.ask < self.bid:
            raise ValueError("invalid_spread")
        return self


class Candle(Contract):
    symbol: str
    timeframe: str
    time: datetime
    open: Decimal = Field(gt=0)
    high: Decimal = Field(gt=0)
    low: Decimal = Field(gt=0)
    close: Decimal = Field(gt=0)
    volume: Decimal = Field(default=Decimal(0), ge=0)

    @model_validator(mode="after")
    def validate_ohlc(self) -> "Candle":
        if (
            self.high < max(self.open, self.close)
            or self.low > min(self.open, self.close)
            or self.low > self.high
        ):
            raise ValueError("invalid_candle")
        return self


class CalendarEvent(Contract):
    id: str
    name: str
    currency: str
    observed_at: datetime
    scheduled_at: datetime
    impact: str
    actual: str | None = None
    forecast: str | None = None
    source: str


TradingWeekday = Literal[
    "MONDAY", "TUESDAY", "WEDNESDAY", "THURSDAY", "FRIDAY", "SATURDAY", "SUNDAY"
]
_CLOCK = r"([01]\d|2[0-3]):[0-5]\d:[0-5]\d"


class TradingSessionWindow(Contract):
    """One broker trade window on the broker server's wall clock; start inclusive.

    An end at or before the start continues past midnight into the next day.
    """

    start: str = Field(pattern="^" + _CLOCK + "$")
    end: str = Field(pattern="^(" + _CLOCK + "|24:00:00)$")


class TradingHours(Contract):
    """Broker-reported trade sessions for one exact symbol; never a market guess.

    Sessions are on the broker server clock. `utc_offset_minutes` is only set when
    the adapter measured it from a broker-timestamped observation.
    """

    symbol: str = Field(min_length=1, max_length=80)
    clock: Literal["broker_server_time"] = "broker_server_time"
    utc_offset_minutes: int | None = Field(default=None, ge=-840, le=840)
    offset_source: str | None = Field(default=None, max_length=80)
    trade_sessions: dict[TradingWeekday, list[TradingSessionWindow]] = Field(
        default_factory=dict[TradingWeekday, list[TradingSessionWindow]]
    )
    trade_mode: str | None = Field(default=None, max_length=80)
    observed_at: datetime
    source: str = Field(min_length=1, max_length=80)
