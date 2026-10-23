from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from lonora_contracts.account import AccountState, Order, Position
from lonora_contracts.market import Candle, Instrument, Quote


def observed(value: Any) -> datetime:
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    if not isinstance(value, str):
        raise ValueError("broker_timestamp_missing")
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def positive_decimal(value: Any) -> Decimal | None:
    """Optional economics must never take down a valid broker price stream."""
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None
    return number if number.is_finite() and number > 0 else None


def currency(value: Any) -> str | None:
    return value if isinstance(value, str) and value.strip() and len(value) <= 80 else None


def instrument(value: dict[str, Any]) -> Instrument:
    return Instrument(
        symbol=value["symbol"],
        description=value.get("description", ""),
        digits=value["digits"],
        tick_size=Decimal(str(value.get("tickSize", value.get("point")))),
        volume_min=value["minVolume"],
        volume_max=value["maxVolume"],
        volume_step=value["volumeStep"],
        stops_level=value.get("stopsLevel", 0),
        point_size=value.get("point"),
        contract_size=positive_decimal(value.get("contractSize")),
        base_currency=currency(value.get("baseCurrency")),
        profit_currency=currency(value.get("profitCurrency")),
    )


def quote(value: dict[str, Any]) -> Quote:
    profit_tick_value = positive_decimal(value.get("profitTickValue"))
    loss_tick_value = positive_decimal(value.get("lossTickValue"))
    return Quote(
        symbol=value["symbol"],
        bid=value["bid"],
        ask=value["ask"],
        observed_at=observed(value["time"]),
        source="metaapi",
        profit_tick_value=profit_tick_value,
        loss_tick_value=loss_tick_value,
        # SDK terminal_state._update_position_profits multiplies these values by
        # lots and price-distance/tickSize, then adds P&L directly to balance.
        # accountCurrencyExchangeRate is a separate reporting conversion: applying
        # it here would convert account-denominated P&L a second time.
        tick_value_basis="account_currency_per_lot"
        if profit_tick_value is not None or loss_tick_value is not None
        else None,
        account_currency_exchange_rate=positive_decimal(value.get("accountCurrencyExchangeRate")),
    )


def candle(value: dict[str, Any], symbol: str, timeframe: str) -> Candle:
    return Candle(
        symbol=value.get("symbol", symbol),
        timeframe=timeframe,
        time=observed(value["time"]),
        open=value["open"],
        high=value["high"],
        low=value["low"],
        close=value["close"],
        volume=value.get("tickVolume", value.get("volume", 0)),
    )


def account(value: dict[str, Any], account_id: str) -> AccountState:
    return AccountState(
        id=account_id,
        broker=str(value["broker"]) if value.get("broker") is not None else None,
        login=str(value["login"]) if value.get("login") is not None else None,
        server=str(value["server"]) if value.get("server") is not None else None,
        name=str(value["name"]) if value.get("name") is not None else None,
        platform=str(value["platform"]) if value.get("platform") is not None else None,
        trade_allowed=value.get("tradeAllowed"),
        investor_mode=value.get("investorMode"),
        currency=value["currency"],
        balance=value["balance"],
        equity=value["equity"],
        margin=value.get("margin", 0),
        free_margin=value.get("freeMargin", 0),
        observed_at=datetime.now(UTC),
    )


def position(value: dict[str, Any]) -> Position:
    return Position(
        id=str(value["id"]),
        symbol=value["symbol"],
        side="buy" if value["type"] == "POSITION_TYPE_BUY" else "sell",
        volume=value["volume"],
        open_price=value["openPrice"],
        profit=value.get("profit", 0),
        stop_loss=value.get("stopLoss"),
        take_profit=value.get("takeProfit"),
        operation_id=value.get("clientId"),
    )


def order(value: dict[str, Any]) -> Order:
    return Order(
        id=str(value["id"]),
        symbol=value["symbol"],
        side=str(value["type"]).removeprefix("ORDER_TYPE_").casefold(),
        volume=value["volume"],
        price=value["openPrice"],
        stop_loss=value.get("stopLoss"),
        take_profit=value.get("takeProfit"),
        operation_id=value.get("clientId"),
    )
