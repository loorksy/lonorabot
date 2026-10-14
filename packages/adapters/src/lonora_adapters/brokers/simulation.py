import asyncio
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from decimal import Decimal
from typing import Any

from lonora_contracts.account import AccountState, Order, Position
from lonora_contracts.domain import new_id, utcnow
from lonora_contracts.market import Candle, Instrument, Quote
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import TradingAccountRow
from sqlalchemy import select


class SimulationBroker:
    """Persistent demo execution using explicitly supplied market snapshots."""

    def __init__(self, db: Database, owner_id: str, connection_id: str):
        self.db, self.owner_id, self.connection_id = db, owner_id, connection_id
        self.closed = False

    async def snapshot(self) -> dict[str, Any]:
        if self.closed:
            raise LonoraError("broker_connection_closed", 409)
        async with self.db.sessions() as session:
            row = await session.scalar(
                select(TradingAccountRow).where(
                    TradingAccountRow.owner_id == self.owner_id,
                    TradingAccountRow.id == self.connection_id,
                )
            )
            if row is None:
                raise LonoraError("simulation_snapshot_required", 409)
            return row.payload

    async def symbols(self) -> list[str]:
        return sorted(item.symbol for item in await self.instruments())

    async def instrument(self, symbol: str) -> Instrument:
        for item in await self.instruments():
            if item.symbol == symbol:
                return item
        raise LonoraError("broker_instrument_unavailable", 404)

    async def instruments(self) -> list[Instrument]:
        return [
            Instrument.model_validate(item)
            for item in (await self.snapshot()).get("instruments", [])
        ]

    async def stream_quotes(self, symbol: str) -> AsyncIterator[Quote]:
        previous: Quote | None = None
        while not self.closed:
            quote = await self.quote(symbol)
            if quote != previous:
                previous = quote
                yield quote
            await asyncio.sleep(1)

    async def quote(self, symbol: str) -> Quote:
        payload = (await self.snapshot()).get("quotes", {}).get(symbol)
        if payload is None:
            raise LonoraError("quote_unavailable", 404)
        return Quote.model_validate(payload)

    async def candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        values = (await self.snapshot()).get("candles", {}).get(symbol + ":" + timeframe, [])
        return [Candle.model_validate(value) for value in values[-limit:]]

    async def history(self, start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
        rows = (await self.snapshot()).get("history", [])
        return [
            row
            for row in rows
            if start <= datetime.fromisoformat(row["time"].replace("Z", "+00:00")) <= end
        ][:limit]

    async def account(self) -> AccountState:
        state = await self.snapshot()
        return AccountState(
            id=self.connection_id,
            broker=state.get("broker"),
            login=str(state["login"]) if state.get("login") is not None else None,
            server=state.get("server"),
            name=state.get("name"),
            platform=state.get("platform"),
            currency=state["currency"],
            balance=state["balance"],
            equity=state.get("equity", state["balance"]),
            margin=state.get("margin", 0),
            free_margin=state.get("free_margin", state["balance"]),
            observed_at=utcnow(),
        )

    async def positions(self) -> list[Position]:
        return [
            Position.model_validate(item) for item in (await self.snapshot()).get("positions", [])
        ]

    async def orders(self) -> list[Order]:
        return [Order.model_validate(item) for item in (await self.snapshot()).get("orders", [])]

    async def execute(
        self, request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        if before_send:
            await before_send()
        async with self.db.sessions() as session, session.begin():
            row = await session.scalar(
                select(TradingAccountRow)
                .where(
                    TradingAccountRow.id == self.connection_id,
                    TradingAccountRow.owner_id == self.owner_id,
                )
                .with_for_update()
            )
            if row is None:
                raise LonoraError("simulation_snapshot_required", 409)
            data = dict(row.payload)
            operations = dict(data.get("operations", {}))
            if request.operation_id in operations:
                return TradeResult.model_validate(operations[request.operation_id])
            positions = list(data.get("positions", []))
            orders = list(data.get("orders", []))
            broker_id: str | None = None
            if request.action in {"buy", "sell"}:
                payload = data.get("quotes", {}).get(request.symbol)
                if payload is None:
                    raise LonoraError("quote_unavailable", 404)
                price = Decimal(str(payload["ask" if request.action == "buy" else "bid"]))
                broker_id = new_id()
                positions.append(
                    Position(
                        id=broker_id,
                        symbol=request.symbol,
                        side=request.action,
                        volume=request.volume or Decimal(0),
                        open_price=price,
                        stop_loss=request.stop_loss,
                        take_profit=request.take_profit,
                        operation_id=request.operation_id,
                    ).model_dump(mode="json")
                )
            elif request.action in {"buy_limit", "sell_limit", "buy_stop", "sell_stop"}:
                broker_id = new_id()
                orders.append(
                    Order(
                        id=broker_id,
                        symbol=request.symbol,
                        side=request.action,
                        volume=request.volume or Decimal(0),
                        price=request.price or Decimal(0),
                        stop_loss=request.stop_loss,
                        take_profit=request.take_profit,
                        operation_id=request.operation_id,
                    ).model_dump(mode="json")
                )
            elif request.action in {"close_position", "modify_position"}:
                target = next(
                    (
                        item
                        for item in positions
                        if item["id"] == request.position_id and item["symbol"] == request.symbol
                    ),
                    None,
                )
                if target is None:
                    raise LonoraError("position_not_found", 404)
                broker_id = str(target["id"])
                if request.action == "close_position":
                    remaining = Decimal(str(target["volume"])) - (
                        request.volume or Decimal(str(target["volume"]))
                    )
                    if remaining < 0:
                        raise LonoraError("position_volume_exceeded", 409)
                    if remaining == 0:
                        positions.remove(target)
                    else:
                        target = {**target, "volume": str(remaining)}
                        positions = [
                            target if item["id"] == request.position_id else item
                            for item in positions
                        ]
                else:
                    target = {
                        **target,
                        "stop_loss": None
                        if request.clear_stop_loss
                        else str(request.stop_loss)
                        if request.stop_loss is not None
                        else target.get("stop_loss"),
                        "take_profit": None
                        if request.clear_take_profit
                        else str(request.take_profit)
                        if request.take_profit is not None
                        else target.get("take_profit"),
                    }
                    positions = [
                        target if item["id"] == request.position_id else item for item in positions
                    ]
            else:
                target = next(
                    (
                        item
                        for item in orders
                        if item["id"] == request.order_id and item["symbol"] == request.symbol
                    ),
                    None,
                )
                if target is None:
                    raise LonoraError("order_not_found", 404)
                broker_id = str(target["id"])
                if request.action == "cancel_order":
                    orders.remove(target)
                else:
                    target = {
                        **target,
                        "price": str(request.price or target["price"]),
                        "stop_loss": None
                        if request.clear_stop_loss
                        else str(request.stop_loss)
                        if request.stop_loss is not None
                        else target.get("stop_loss"),
                        "take_profit": None
                        if request.clear_take_profit
                        else str(request.take_profit)
                        if request.take_profit is not None
                        else target.get("take_profit"),
                    }
                    orders = [target if item["id"] == request.order_id else item for item in orders]
            result = TradeResult(
                operation_id=request.operation_id,
                status="confirmed",
                broker_id=broker_id,
                details={"simulation": True},
            )
            operations[request.operation_id] = result.model_dump(mode="json")
            row.payload = {
                **data,
                "positions": positions,
                "orders": orders,
                "operations": operations,
            }
            row.version += 1
            return result

    async def reconcile(
        self, operation_id: str, request: TradeRequest | None = None
    ) -> TradeResult:
        value = (await self.snapshot()).get("operations", {}).get(operation_id)
        return (
            TradeResult.model_validate(value)
            if value
            else TradeResult(
                operation_id=operation_id, status="ambiguous", code="execution_not_observed"
            )
        )

    async def close(self) -> None:
        self.closed = True
