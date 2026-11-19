"""A MetaApi account as the API process sees it: every read is answered by the Gateway.

Only the Gateway keeps MetaApi connections (one subscription and one synchronization owner
per account). The API process never opens one: it asks the Gateway through the broker
relay (``lonora_db.broker_relay``). An owner's direct order is handed over whole, as an
execution, never as a send (``ExecutionService.execute`` runs in the Gateway).
"""

from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime
from typing import Any

from lonora_contracts.account import AccountState, Order, Position
from lonora_contracts.market import Candle, Instrument, Quote, TradingHours
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_core.user_error import LonoraError
from lonora_db.broker_relay import ask
from lonora_db.client import Database
from pydantic import TypeAdapter

READ_SECONDS = 45.0
EXECUTE_SECONDS = 60.0

# Each relayed read: the adapter method's name, its argument names, and its result type.
READS: dict[str, tuple[tuple[str, ...], TypeAdapter[Any]]] = {
    "account": ((), TypeAdapter(AccountState)),
    "positions": ((), TypeAdapter(list[Position])),
    "orders": ((), TypeAdapter(list[Order])),
    "symbols": ((), TypeAdapter(list[str])),
    "instruments": ((), TypeAdapter(list[Instrument])),
    "instrument": (("symbol",), TypeAdapter(Instrument)),
    "trading_hours": (("symbol",), TypeAdapter(TradingHours)),
    "quote": (("symbol",), TypeAdapter(Quote)),
    "candles": (("symbol", "timeframe", "limit"), TypeAdapter(list[Candle])),
}


async def perform(broker: Any, kind: str, arguments: dict[str, Any]) -> Any:
    """The Gateway's side of a relayed read: call its own adapter, answer in JSON."""
    names, result = READS[kind]
    values = [arguments[name] for name in names]
    return result.dump_python(await getattr(broker, kind)(*values), mode="json")


class RelayedBroker:
    def __init__(self, db: Database, owner_id: str, connection_id: str):
        self.db, self.owner_id, self.connection_id = db, owner_id, connection_id
        self.closed = False

    async def _read(self, kind: str, *values: Any) -> Any:
        names, result = READS[kind]
        arguments = dict(zip(names, values, strict=True))
        answer = await ask(
            self.db, self.owner_id, self.connection_id, kind, arguments, READ_SECONDS
        )
        return result.validate_python(answer)

    async def account(self) -> AccountState:
        return await self._read("account")

    async def positions(self) -> list[Position]:
        return await self._read("positions")

    async def orders(self) -> list[Order]:
        return await self._read("orders")

    async def symbols(self) -> list[str]:
        return await self._read("symbols")

    async def instruments(self) -> list[Instrument]:
        return await self._read("instruments")

    async def instrument(self, symbol: str) -> Instrument:
        return await self._read("instrument", symbol)

    async def trading_hours(self, symbol: str) -> TradingHours:
        return await self._read("trading_hours", symbol)

    async def quote(self, symbol: str) -> Quote:
        return await self._read("quote", symbol)

    async def candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        return await self._read("candles", symbol, timeframe, limit)

    async def history(self, start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
        # Deal history is read by the Gateway's own steps (closed trades, reconciliation).
        raise LonoraError("broker_read_in_gateway", 409)

    def stream_quotes(self, symbol: str) -> AsyncIterator[Quote]:
        raise LonoraError("broker_stream_in_gateway", 409)

    def stream_candles(self, symbol: str, timeframe: str) -> AsyncIterator[Candle]:
        raise LonoraError("broker_stream_in_gateway", 409)

    async def execute(
        self, request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        # A send is never relayed: the whole execution runs in the Gateway (execute_order).
        raise LonoraError("broker_send_in_gateway", 409)

    async def reconcile(
        self,
        operation_id: str,
        request: TradeRequest | None = None,
        *,
        submitted_at: datetime | None = None,
    ) -> TradeResult:
        raise LonoraError("broker_send_in_gateway", 409)

    async def close(self) -> None:
        self.closed = True


async def execute_order(db: Database, owner_id: str, request: TradeRequest) -> TradeResult:
    """An owner's direct order on a MetaApi account, executed by the Gateway's
    ``ExecutionService`` (journal, checks and send unchanged). Repeating it with the same
    operation_id returns the journal's receipt."""
    answer = await ask(
        db,
        owner_id,
        request.account_id,
        "execute",
        request.model_dump(mode="json"),
        EXECUTE_SECONDS,
    )
    return TradeResult.model_validate(answer)
