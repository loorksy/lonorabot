"""One adapter contract, run against the simulation broker, MetaApi fixtures and Alpaca.

What the single executor relies on from every broker adapter: reads return the shared
contracts; ``execute`` awaits ``before_send`` exactly once and sends nothing when it
raises; an acknowledged entry appears in ``positions()`` and closes again; and
``reconcile`` never invents an outcome for an operation it has no evidence of. The
simulation case needs the migrated PostgreSQL schema (skipped without
``LONORA_DATABASE_URL``); the others need no database and no network.
"""

import os
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from uuid import uuid4

import pytest
import pytest_asyncio
from lonora_adapter_kit.broker import BrokerAdapter
from lonora_contracts.account import AccountState, Order, Position
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Candle, Instrument, Quote
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError


@dataclass
class Case:
    broker: BrokerAdapter
    account_id: str
    symbol: str
    timeframe: str
    volume: Decimal
    sent: Callable[[], Awaitable[int]]  # broker mutations observed so far


async def alpaca_case(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Case]:
    from alpaca_fake import KEY_ID, SECRET_KEY, FakeAlpaca
    from lonora_adapters.brokers import alpaca

    fake = FakeAlpaca()
    monkeypatch.setattr(alpaca, "transport_factory", fake.transport)
    broker = alpaca.AlpacaBroker(KEY_ID, SECRET_KEY, "alpaca-conn")

    async def sent() -> int:
        return len(fake.mutations)

    yield Case(broker, "alpaca-conn", "AAPL", "1h", Decimal(3), sent)
    await broker.close()


class MetaApiRpc:
    """Scripted MetaApi RPC: official response shapes, an in-memory hedging book."""

    def __init__(self) -> None:
        self.positions: list[dict[str, Any]] = []
        self.mutations = 0

    async def get_account_information(self) -> dict[str, Any]:
        return {
            "broker": "Fixture Ltd",
            "login": 1234,
            "server": "Fixture-Demo",
            "platform": "mt5",
            "currency": "USD",
            "balance": 10000,
            "equity": 10000,
            "margin": 0,
            "freeMargin": 10000,
            "tradeAllowed": True,
        }

    async def get_symbols(self) -> list[str]:
        return ["EURUSD"]

    async def get_symbol_specification(self, symbol: str) -> dict[str, Any]:
        return {
            "symbol": symbol,
            "digits": 5,
            "tickSize": 0.00001,
            "point": 0.00001,
            "minVolume": 0.01,
            "maxVolume": 100,
            "volumeStep": 0.01,
            "contractSize": 100000,
        }

    async def get_symbol_price(self, symbol: str) -> dict[str, Any]:
        return {"symbol": symbol, "bid": 1.1, "ask": 1.1002, "time": utcnow().isoformat()}

    async def get_positions(self) -> list[dict[str, Any]]:
        return list(self.positions)

    async def get_orders(self) -> list[dict[str, Any]]:
        return []

    async def create_market_buy_order(
        self, symbol: str, volume: float, **options: Any
    ) -> dict[str, Any]:
        self.mutations += 1
        ticket = str(1000 + self.mutations)
        self.positions.append(
            {
                "id": ticket,
                "symbol": symbol,
                "type": "POSITION_TYPE_BUY",
                "volume": volume,
                "openPrice": 1.1002,
                "clientId": options["options"]["clientId"],
            }
        )
        return {"stringCode": "TRADE_RETCODE_DONE", "numericCode": 10009, "positionId": ticket}

    async def close_position(self, position_id: str, **options: Any) -> dict[str, Any]:
        self.mutations += 1
        self.positions = [p for p in self.positions if p["id"] != position_id]
        return {"stringCode": "TRADE_RETCODE_DONE", "numericCode": 10009, "positionId": position_id}

    async def get_deals_by_time_range(self, *args: Any) -> dict[str, Any]:
        return {"deals": []}

    async def get_history_orders_by_time_range(self, *args: Any) -> dict[str, Any]:
        return {"historyOrders": []}


async def metaapi_case(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Case]:
    import asyncio

    from lonora_adapters.brokers.metaapi import MetaApiBroker

    rpc = MetaApiRpc()
    broker: Any = object.__new__(MetaApiBroker)
    broker.connection_id, broker.account_id = "metaapi-conn", "provider-account"
    broker.account_instance = None
    broker.evidence, broker.evidence_lock = None, asyncio.Lock()
    broker.streaming = None
    broker._log_redactions = ()

    async def read(method: str, *args: Any) -> Any:
        return await getattr(rpc, method)(*args)

    async def prepare() -> Any:
        return rpc

    async def history(symbol: str, timeframe: str, start_time: Any, limit: int) -> Any:
        return [
            {"time": "2026-11-10T10:00:00Z", "open": 1.1, "high": 1.2, "low": 1.0, "close": 1.15},
            {"time": "2026-11-10T11:00:00Z", "open": 1.15, "high": 1.2, "low": 1.1, "close": 1.1},
        ][-limit:]

    async def resolve() -> Any:
        return SimpleNamespace(get_historical_candles=history)

    async def no_stream() -> Any:
        # No streaming terminal: catalog reads fall back to RPC, as in production.
        raise LonoraError("broker_connection_unavailable", 503)

    broker.read_rpc, broker.prepare, broker.resolve_account = read, prepare, resolve
    broker.prepare_stream = no_stream

    async def sent() -> int:
        return rpc.mutations

    yield Case(broker, "metaapi-conn", "EURUSD", "1h", Decimal("0.1"), sent)


async def simulation_case(monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[Case]:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The simulation broker uses the real migrated PostgreSQL schema.")
    from check_streaming import Fixture
    from lonora_adapters.brokers.simulation import SimulationBroker
    from lonora_db.schema import TradingAccountRow
    from test_proactive_wakes import retire, simulation

    fixture = await Fixture().open()
    connection = await simulation(fixture)
    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(TradingAccountRow, connection, with_for_update=True)
        assert row is not None
        row.payload = {
            **row.payload,
            "candles": {
                "XAUUSD:1h": [
                    {
                        "symbol": "XAUUSD",
                        "timeframe": "1h",
                        "time": "2026-11-10T10:00:00Z",
                        "open": "100",
                        "high": "102",
                        "low": "99",
                        "close": "101",
                    }
                ]
            },
        }
    broker = SimulationBroker(fixture.runtime.db, fixture.owner, connection)

    async def sent() -> int:
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(TradingAccountRow, connection, populate_existing=True)
            assert row is not None
            return len(row.payload.get("operations", {}))

    yield Case(broker, connection, "XAUUSD", "1h", Decimal("0.1"), sent)
    await broker.close()
    await retire(fixture, connection)
    await fixture.client.aclose()


CASES = {"alpaca": alpaca_case, "metaapi": metaapi_case, "simulation": simulation_case}


@pytest_asyncio.fixture(params=sorted(CASES))
async def case(
    request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch
) -> AsyncIterator[Case]:
    async for value in CASES[request.param](monkeypatch):
        yield value


def entry(case: Case) -> TradeRequest:
    return TradeRequest(
        account_id=case.account_id, action="buy", symbol=case.symbol, volume=case.volume
    )


async def positions_of(case: Case) -> list[Position]:
    return [p for p in await case.broker.positions() if p.symbol == case.symbol]


@pytest.mark.asyncio
async def test_reads_return_the_shared_contracts(case: Case) -> None:
    account = await case.broker.account()
    assert isinstance(account, AccountState) and account.currency
    instruments = await case.broker.instruments()
    assert all(isinstance(item, Instrument) for item in instruments)
    assert case.symbol in await case.broker.symbols()
    assert (await case.broker.instrument(case.symbol)).symbol == case.symbol
    quote = await case.broker.quote(case.symbol)
    assert isinstance(quote, Quote) and quote.symbol == case.symbol and quote.bid <= quote.ask
    candles = await case.broker.candles(case.symbol, case.timeframe, 2)
    assert candles and all(isinstance(c, Candle) for c in candles)
    assert all(c.symbol == case.symbol and c.timeframe == case.timeframe for c in candles)
    assert candles == sorted(candles, key=lambda c: c.time)
    assert all(isinstance(p, Position) for p in await case.broker.positions())
    assert all(isinstance(o, Order) for o in await case.broker.orders())


@pytest.mark.asyncio
async def test_a_refused_boundary_sends_nothing(case: Case) -> None:
    before = len(await positions_of(case))
    mutations = await case.sent()

    async def refuse() -> None:
        raise LonoraError("trading_disabled", 409)

    with pytest.raises(LonoraError) as refused:
        await case.broker.execute(entry(case), refuse)
    assert refused.value.code == "trading_disabled"
    assert await case.sent() == mutations and len(await positions_of(case)) == before


@pytest.mark.asyncio
async def test_entry_crosses_the_boundary_once_then_closes(case: Case) -> None:
    calls: list[int] = []

    async def before_send() -> None:
        calls.append(await case.sent())

    request = entry(case)
    result = await case.broker.execute(request, before_send)
    assert calls == [calls[0]] and result.operation_id == request.operation_id
    assert result.status == "confirmed"
    opened = await positions_of(case)
    assert any(p.side == "buy" for p in opened)
    target = next(p for p in opened if p.side == "buy")
    close = TradeRequest(
        account_id=case.account_id,
        action="close_position",
        symbol=case.symbol,
        position_id=target.id,
    )
    closed = await case.broker.execute(close, before_send)
    assert closed.status == "confirmed" and len(calls) == 2
    assert all(p.id != target.id for p in await positions_of(case))


@pytest.mark.asyncio
async def test_reconcile_never_invents_an_outcome(case: Case) -> None:
    unknown = entry(case).model_copy(update={"operation_id": "never-sent-" + uuid4().hex})
    result = await case.broker.reconcile(unknown.operation_id, unknown, submitted_at=utcnow())
    assert result.status == "ambiguous" and result.operation_id == unknown.operation_id
