from datetime import UTC, datetime
from decimal import Decimal
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


def instrument(value: dict[str, Any]) -> Instrument:
    return Instrument(
        symbol=value["symbol"],
        description=value.get("description", ""),
        digits=value["digits"],
        tick_size=Decimal(str(value.get("tickSize", value.get("point")))),
        volume_min=value["minVolume"],
        volume_max=value["maxVolume"],
        volume_step=value["volumeStep"],
    )


def quote(value: dict[str, Any]) -> Quote:
    return Quote(
        symbol=value["symbol"],
        bid=value["bid"],
        ask=value["ask"],
        observed_at=observed(value["time"]),
        source="metaapi",
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
