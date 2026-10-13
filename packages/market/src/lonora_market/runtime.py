"""Resident broker-neutral observations. PostgreSQL snapshots survive process/browser loss."""

import asyncio
import time
from collections.abc import Iterable
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Candle, Instrument, Quote
from lonora_core.chart_controller import validate_timeframe
from lonora_core.trading_run_market import require_exact_symbol
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.market_snapshots import save_snapshot, snapshot_id
from lonora_db.schema import BrokerSessionRow, CloudChartRow, MarketSnapshotRow, MarketWatchRow
from sqlalchemy import select

from .candles import validate_candle_series


class RuntimeMarketAdapter:
    def __init__(self, runtime: "MarketRuntime", connection_id: str):
        self.runtime, self.connection_id = runtime, connection_id

    async def instruments(self) -> list[Instrument]:
        return await (
            await self.runtime.brokers.get(self.runtime.owner_id, self.connection_id)
        ).instruments()

    async def quote(self, symbol: str) -> Quote:
        return await self.runtime.quote(self.connection_id, symbol)

    async def candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        return await self.runtime.candles(self.connection_id, symbol, timeframe, limit)


class MarketRuntime:
    def __init__(self, db: Database, brokers: BrokerManager, owner_id: str):
        self.db, self.brokers, self.owner_id = db, brokers, owner_id
        self.tasks: dict[tuple[str, str], asyncio.Task[None]] = {}
        self.versions: dict[tuple[str, str], int] = {}
        self.last_events: dict[tuple[str, str], float] = {}
        self.closed = False
        self.identity = "market-stream:" + uuid4().hex
        self.fetch_slots = asyncio.Semaphore(8)

    async def cached(
        self, connection_id: str, symbol: str, timeframe: str, ttl: int
    ) -> dict[str, Any] | None:
        async with self.db.sessions() as session:
            connection = await session.get(BrokerSessionRow, connection_id)
            if connection is None or connection.owner_id != self.owner_id:
                raise LonoraError("broker_sessions_not_found", 404)
            if not connection.payload.get("enabled"):
                raise LonoraError("broker_disabled", 409)
            row = await session.get(
                MarketSnapshotRow, snapshot_id(self.owner_id, connection_id, symbol, timeframe)
            )
            if (
                row
                and row.connection_version == connection.version
                and row.updated_at > utcnow() - timedelta(seconds=ttl)
            ):
                return row.payload
        return None

    async def store(
        self,
        connection_id: str,
        symbol: str,
        timeframe: str,
        payload: dict[str, Any],
        expected_version: int | None = None,
        stream_owner: str | None = None,
    ) -> bool:
        async with self.db.sessions() as session, session.begin():
            return await save_snapshot(
                session,
                self.owner_id,
                connection_id,
                symbol,
                timeframe,
                payload,
                expected_version,
                stream_owner,
            )

    async def quote(self, connection_id: str, symbol: str) -> Quote:
        cached = await self.cached(connection_id, symbol, "", 15)
        if cached:
            return Quote.model_validate(cached)
        async with self.fetch_slots:
            broker = await self.brokers.get(self.owner_id, connection_id)
            version = self.brokers.connections[connection_id][0]
            quote = await broker.quote(symbol)
            require_exact_symbol(symbol, quote.symbol)
            await self.store(
                connection_id,
                symbol,
                "",
                quote.model_dump(mode="json"),
                version,
            )
            return quote

    async def candles(
        self, connection_id: str, symbol: str, timeframe: str, limit: int = 500
    ) -> list[Candle]:
        validate_timeframe(timeframe)
        cached = await self.cached(connection_id, symbol, timeframe, 15)
        if cached and int(cached.get("limit", 0)) >= limit:
            return [Candle.model_validate(value) for value in cached["candles"]][-limit:]
        async with self.fetch_slots:
            broker = await self.brokers.get(self.owner_id, connection_id)
            version = self.brokers.connections[connection_id][0]
            candles = validate_candle_series(await broker.candles(symbol, timeframe, limit))
            for candle in candles:
                require_exact_symbol(symbol, candle.symbol)
            await self.store(
                connection_id,
                symbol,
                timeframe,
                {
                    "candles": [value.model_dump(mode="json") for value in candles],
                    "limit": limit,
                },
                version,
            )
            return candles

    async def consume(self, connection_id: str, symbol: str) -> None:
        failures = 0
        while not self.closed:
            try:
                broker = await self.brokers.get(self.owner_id, connection_id)
                async for quote in broker.stream_quotes(symbol):
                    require_exact_symbol(symbol, quote.symbol)
                    accepted = await self.store(
                        connection_id,
                        symbol,
                        "",
                        quote.model_dump(mode="json"),
                        self.versions.get((connection_id, symbol)),
                        self.identity,
                    )
                    if accepted:
                        from .watchers import check_watches

                        await check_watches(
                            self.db,
                            self.brokers,
                            price_update=quote,
                            connection_id=connection_id,
                            owner_id=self.owner_id,
                        )
                    key = (connection_id, symbol)
                    if accepted and time.monotonic() - self.last_events.get(key, 0) >= 1:
                        async with self.db.sessions() as session, session.begin():
                            emit(
                                session,
                                self.owner_id,
                                "market.quote_updated",
                                payload={
                                    "connection_id": connection_id,
                                    "symbol": symbol,
                                    "quote": quote.model_dump(mode="json"),
                                },
                            )
                        self.last_events[key] = time.monotonic()
                    failures = 0
            except asyncio.CancelledError:
                raise
            except Exception:
                failures += 1
            await asyncio.sleep(min(30, 2 ** min(failures, 5)))

    async def synchronize(self, targets: Iterable[tuple[str, str]]) -> None:
        async with self.db.sessions() as session:
            connections = {
                row.id: row
                for row in (
                    await session.scalars(
                        select(BrokerSessionRow).where(BrokerSessionRow.owner_id == self.owner_id)
                    )
                ).all()
                if row.payload.get("enabled")
            }
        requested = {key for key in targets if key[0] in connections}
        allowed: set[str] = set()
        async with self.db.sessions() as session, session.begin():
            for connection_id in sorted({key[0] for key in requested}):
                row = await session.get(BrokerSessionRow, connection_id, with_for_update=True)
                if row is None or row.owner_id != self.owner_id or not row.payload.get("enabled"):
                    continue
                expires = row.state.get("market_stream_until")
                if (
                    row.state.get("market_stream_owner") != self.identity
                    and expires
                    and datetime.fromisoformat(expires) > utcnow()
                ):
                    continue
                row.state = {
                    **row.state,
                    "market_stream_owner": self.identity,
                    "market_stream_until": (utcnow() + timedelta(seconds=60)).isoformat(),
                }
                allowed.add(connection_id)
        wanted = {key for key in requested if key[0] in allowed}
        for key, task in list(self.tasks.items()):
            if (
                key not in wanted
                or self.versions.get(key) != connections[key[0]].version
                or task.done()
            ):
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                del self.tasks[key]
                self.versions.pop(key, None)
                self.last_events.pop(key, None)
        for connection_id, symbol in sorted(wanted - self.tasks.keys()):
            key = (connection_id, symbol)
            self.versions[key] = connections[connection_id].version
            self.tasks[key] = asyncio.create_task(
                self.consume(*key), name="market:" + connection_id + ":" + symbol
            )

    async def maintain(self) -> None:
        # Renewal is a separate gateway loop: slow chart history requests must not
        # expire a healthy stream's account lease.
        async with self.db.sessions() as session:
            chart_payloads = (
                await session.scalars(
                    select(CloudChartRow.payload).where(CloudChartRow.owner_id == self.owner_id)
                )
            ).all()
            watch_payloads = (
                await session.scalars(
                    select(MarketWatchRow.payload).where(MarketWatchRow.owner_id == self.owner_id)
                )
            ).all()
        targets = {(str(value["account_id"]), str(value["symbol"])) for value in chart_payloads}
        targets.update(
            (str(value["account_id"]), str(value["symbol"]))
            for value in watch_payloads
            if value.get("enabled", True) and value.get("kind", "price") in {"price", "indicator"}
        )
        await self.synchronize(targets)

    async def close(self) -> None:
        self.closed = True
        for task in self.tasks.values():
            task.cancel()
        await asyncio.gather(*self.tasks.values(), return_exceptions=True)
        self.tasks.clear()
        async with self.db.sessions() as session, session.begin():
            rows = (
                await session.scalars(
                    select(BrokerSessionRow)
                    .where(BrokerSessionRow.owner_id == self.owner_id)
                    .with_for_update()
                )
            ).all()
            for row in rows:
                if row.state.get("market_stream_owner") == self.identity:
                    row.state = {
                        **row.state,
                        "market_stream_until": None,
                        "market_stream_owner": None,
                    }
