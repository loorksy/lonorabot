"""Resident broker-neutral observations. PostgreSQL snapshots survive process/browser loss."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Iterable
from datetime import datetime, timedelta
from typing import Any
from uuid import uuid4

from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Candle, Instrument, Quote
from lonora_core.chart_controller import validate_timeframe
from lonora_core.error_logging import safe_exception_message
from lonora_core.trading_run_market import require_exact_symbol
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.market_snapshots import save_snapshot, snapshot_id
from lonora_db.schema import BrokerSessionRow, CloudChartRow, MarketSnapshotRow, MarketWatchRow
from sqlalchemy import select

from .candle_store import merge_candle, merge_history
from .candles import validate_candle_series

logger = logging.getLogger(__name__)


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
        self.candle_tasks: dict[tuple[str, str, str], asyncio.Task[None]] = {}
        self.candle_versions: dict[tuple[str, str, str], int] = {}
        self.on_update: Callable[[str, str, str | None, str], Awaitable[None]] | None = None
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
        cached = await self.cached(connection_id, symbol, timeframe, 60)
        if (
            cached
            and int(cached.get("limit", 0)) >= limit
            and cached.get("history_updated_at")
            and datetime.fromisoformat(cached["history_updated_at"])
            > utcnow() - timedelta(seconds=60)
        ):
            return [Candle.model_validate(value) for value in cached["candles"]][-limit:]
        async with self.fetch_slots:
            broker = await self.brokers.get(self.owner_id, connection_id)
            version = self.brokers.connections[connection_id][0]
            requested_at = utcnow()
            candles = validate_candle_series(await broker.candles(symbol, timeframe, limit))
            for candle in candles:
                require_exact_symbol(symbol, candle.symbol)
            async with self.db.sessions() as session, session.begin():
                return await merge_history(
                    session,
                    self.owner_id,
                    connection_id,
                    symbol,
                    timeframe,
                    candles,
                    limit,
                    version,
                    requested_at,
                )

    async def notify(self, connection_id: str, symbol: str, timeframe: str | None) -> None:
        if self.on_update:
            try:
                await self.on_update(connection_id, symbol, timeframe, self.identity)
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning(
                    "market_scene_update_failed error_type=%s message=%s",
                    type(error).__name__,
                    safe_exception_message(error),
                )

    async def consume(self, connection_id: str, symbol: str) -> None:
        failures = 0
        version = self.versions[(connection_id, symbol)]
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
                        version,
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
                    if accepted:
                        await self.notify(connection_id, symbol, None)
                    failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning(
                    "market_stream_failed error_type=%s message=%s",
                    type(error).__name__,
                    safe_exception_message(error),
                )
                failures += 1
            await asyncio.sleep(min(30, 2 ** min(failures, 5)))

    async def consume_candles(self, connection_id: str, symbol: str, timeframe: str) -> None:
        failures = 0
        version = self.candle_versions[(connection_id, symbol, timeframe)]
        while not self.closed:
            try:
                broker = await self.brokers.get(self.owner_id, connection_id)
                async for candle in broker.stream_candles(symbol, timeframe):
                    require_exact_symbol(symbol, candle.symbol)
                    if candle.timeframe != timeframe:
                        raise LonoraError("broker_candle_timeframe_mismatch", 502)
                    async with self.db.sessions() as session, session.begin():
                        accepted = await merge_candle(
                            session,
                            self.owner_id,
                            connection_id,
                            candle,
                            version,
                            self.identity,
                        )
                    if accepted:
                        await self.notify(connection_id, symbol, timeframe)
                        from .watchers import check_watches

                        await check_watches(
                            self.db,
                            self.brokers,
                            candle_update=candle,
                            connection_id=connection_id,
                            owner_id=self.owner_id,
                        )
                    failures = 0
            except asyncio.CancelledError:
                raise
            except Exception as error:
                logger.warning(
                    "market_stream_failed error_type=%s message=%s",
                    type(error).__name__,
                    safe_exception_message(error),
                )
                failures += 1
            await asyncio.sleep(min(30, 2 ** min(failures, 5)))

    async def synchronize_candles(self, targets: Iterable[tuple[str, str, str]]) -> None:
        wanted = {key for key in targets if key[:2] in self.tasks}
        for key, task in list(self.candle_tasks.items()):
            if (
                key not in wanted
                or task.done()
                or self.candle_versions.get(key) != self.versions.get(key[:2])
            ):
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                del self.candle_tasks[key]
                self.candle_versions.pop(key, None)
        for key in sorted(wanted - self.candle_tasks.keys()):
            self.candle_versions[key] = self.versions[key[:2]]
            self.candle_tasks[key] = asyncio.create_task(
                self.consume_candles(*key), name="candles:" + ":".join(key)
            )

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
        candle_targets = {
            (str(value["account_id"]), str(value["symbol"]), str(value.get("timeframe", "1h")))
            for value in chart_payloads
        }
        candle_targets.update(
            (str(value["account_id"]), str(value["symbol"]), str(value.get("timeframe", "1h")))
            for value in watch_payloads
            if value.get("enabled", True) and value.get("kind") == "indicator"
        )
        await self.synchronize_candles(candle_targets)

    async def close(self) -> None:
        self.closed = True
        for task in [*self.tasks.values(), *self.candle_tasks.values()]:
            task.cancel()
        await asyncio.gather(
            *self.tasks.values(), *self.candle_tasks.values(), return_exceptions=True
        )
        self.tasks.clear()
        self.candle_tasks.clear()
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
