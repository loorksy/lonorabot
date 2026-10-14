"""Actual SDK registry/wrappers with scripted transports; no live account mutations."""

import asyncio
import importlib
from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace
from typing import Any
from unittest.mock import AsyncMock, patch

from lonora_adapters.brokers.metaapi import MetaApiBroker
from lonora_adapters.brokers.metaapi_lifecycle import history_storage
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError

ConnectionRegistry: Any = importlib.import_module(
    "metaapi_cloud_sdk.metaapi.connection_registry"
).ConnectionRegistry
MetatraderAccount: Any = importlib.import_module(
    "metaapi_cloud_sdk.metaapi.metatrader_account"
).MetatraderAccount


class SharedConnection:
    def __init__(self, kind: str, account: Any, registry: Any):
        self.kind, self.account, self.registry = kind, account, registry
        self._closed = False
        self.application = "RPC"
        self.terminal_state: Any = SimpleNamespace()
        self.terminal_state.price = self.no_price
        self.synchronized = False
        self.instances: set[str] = set()
        self.waits = 0
        self.failure: Exception | None = None
        self.gate: asyncio.Event | None = None

    @staticmethod
    def no_price(symbol: str) -> None:
        return None

    def is_synchronized(self) -> bool:
        return self.synchronized

    async def connect(self, instance_id: str) -> None:
        self.instances.add(instance_id)
        await asyncio.sleep(0)

    async def close(self, instance_id: str) -> None:
        self.instances.discard(instance_id)
        if not self.instances and not self._closed:
            await asyncio.sleep(0)
            await getattr(self.registry, "remove_" + self.kind)(self.account)
            self._closed = True

    async def wait_synchronized(self, options: Any) -> None:
        assert options == 15 or options == {"timeoutInSeconds": 15}
        self.waits += 1
        if self.gate:
            await self.gate.wait()
        if self.failure:
            raise self.failure
        self.synchronized = True


class Harness:
    def __init__(self):
        self.websocket: Any = SimpleNamespace(
            region=None,
            unsubscribe=AsyncMock(),
            get_symbols=AsyncMock(return_value=["EURUSD.m", "XAUUSD.a", "BTCUSD+", "US500.cash"]),
            get_symbol_price=AsyncMock(
                return_value={"symbol": "EURUSD.m", "bid": 1, "ask": 2, "time": datetime.now(UTC)}
            ),
            trade=AsyncMock(side_effect=TimeoutError("Scripted response lost")),
            remove_synchronization_listener=AsyncMock(),
        )
        self.registry: Any = ConnectionRegistry({}, self.websocket, SimpleNamespace())
        self.account: Any = object.__new__(MetatraderAccount)
        self.account._data = {
            "_id": "test-account",
            "region": "london",
            "accountReplicas": [],
            "reliability": "regular",
            "type": "cloud-g2",
            "version": 5,
        }
        self.account._replicas = []
        self.account._connection_registry = self.registry
        self.account._metaapi_websocket_client = self.websocket
        self.created: dict[str, list[SharedConnection]] = {"rpc": [], "streaming": []}
        self.next_failure: Exception | None = None
        self.next_gate: asyncio.Event | None = None
        self.broker: Any = object.__new__(MetaApiBroker)
        self.broker.account_id = "test-account"
        self.broker.account_instance = self.account
        self.broker.account_lock = asyncio.Lock()
        self.broker.lock = asyncio.Lock()
        self.broker.stream_lock = asyncio.Lock()
        self.broker.rpc = None
        self.broker.streaming = None
        self.broker._log_redactions = ("private-token", "test-account")

    def make(self, kind: str, *args: Any) -> SharedConnection:
        account, registry = (args[2], args[3]) if kind == "rpc" else (args[3], args[5])
        connection = SharedConnection(kind, account, registry)
        connection.failure, self.next_failure = self.next_failure, None
        connection.gate, self.next_gate = self.next_gate, None
        self.created[kind].append(connection)
        return connection

    def patches(self) -> tuple[Any, Any]:
        def rpc_factory(*args: Any) -> SharedConnection:
            return self.make("rpc", *args)

        def stream_factory(*args: Any) -> SharedConnection:
            return self.make("streaming", *args)

        return (
            patch(
                "metaapi_cloud_sdk.metaapi.connection_registry.RpcMetaApiConnection",
                rpc_factory,
            ),
            patch(
                "metaapi_cloud_sdk.metaapi.connection_registry.StreamingMetaApiConnection",
                stream_factory,
            ),
        )


async def main() -> None:
    h = Harness()
    rpc_patch, stream_patch = h.patches()
    with rpc_patch, stream_patch:
        first = await h.broker.prepare()
        assert h.created["rpc"][0].waits == 1
        assert all(
            value is first
            for value in await asyncio.gather(*(h.broker.prepare() for _ in range(40)))
        )
        assert h.created["rpc"][0].waits == 1
        # Reproduce closed wrapper still registered against its old shared connection.
        first._closed = True
        results = await asyncio.gather(*(h.broker.prepare() for _ in range(40)))
        replacement = results[0]
        assert replacement is not first and all(value is replacement for value in results)
        assert len(h.created["rpc"]) == 2
        await asyncio.sleep(0)
        assert h.registry.rpc_connections[h.account.id] is replacement._meta_api_connection
        print(
            "PASS actual SDK closed wrapper/registry replaced once under 40 concurrent callers; healthy RPC skips repeated synchronization"
        )

        # Failure occurring after prepare but before a read response can retry only the read.
        h.websocket.get_symbols.side_effect = [
            Exception("This connection has been closed, please create a new connection"),
            ["BTCUSD+"],
        ]
        assert await h.broker.symbols() == ["BTCUSD+"]
        assert len(h.created["rpc"]) == 3
        print(
            "PASS closed read connection is evicted from actual SDK registry and safe read recovers with exact broker symbol"
        )

        request = TradeRequest(
            account_id="fixture",
            operation_id="one-send",
            action="buy",
            symbol="EURUSD.m",
            volume=Decimal("0.01"),
        )
        before = AsyncMock()
        result = await h.broker.execute(request, before)
        assert result.status == "ambiguous"
        before.assert_awaited_once()
        h.websocket.trade.assert_awaited_once()
        # A definitely closed error after the journal send boundary is still not retried.
        h.websocket.trade.side_effect = Exception(
            "This connection has been closed, please create a new connection"
        )
        result = await h.broker.execute(request, before)
        assert result.status == "ambiguous" and h.broker.rpc is None
        assert h.websocket.trade.await_count == 2
        print(
            "PASS timeout/closed financial response sends once per invocation, remains ambiguous, and only future operations get a fresh connection"
        )

        old_stream = await h.broker.prepare_stream()
        old_stream._closed = True
        streams = await asyncio.gather(*(h.broker.prepare_stream() for _ in range(40)))
        fresh_stream = streams[0]
        assert fresh_stream is not old_stream and all(value is fresh_stream for value in streams)
        await h.broker.invalidate("streaming", old_stream)
        assert h.broker.streaming is fresh_stream
        assert h.registry.streaming_connections[h.account.id] is fresh_stream._meta_api_connection
        assert len(h.created["streaming"]) == 2
        raw = {"symbol": "BTCUSD+", "bid": 60000, "ask": 60001, "time": datetime.now(UTC)}

        def live_price(symbol: str) -> dict[str, Any] | None:
            return raw if symbol == raw["symbol"] else None

        fresh_stream._meta_api_connection.terminal_state.price = live_price
        with patch.object(
            MetaApiBroker, "prepare", AsyncMock(side_effect=TimeoutError("RPC startup"))
        ) as prepare:
            quote = await h.broker.quote("BTCUSD+")
            assert quote.symbol == "BTCUSD+" and quote.bid == 60000
            prepare.assert_not_awaited()
        print(
            "PASS actual SDK streamed price remains available during independent RPC startup failure"
        )
        print(
            "PASS candle/quote consumers share one fresh streaming wrapper and stale finalizers cannot evict a replacement"
        )

    h = Harness()
    rpc_patch, stream_patch = h.patches()
    with rpc_patch, stream_patch:
        h.next_failure = TimeoutError("waitSynchronized timed out for test-account")
        failures = await asyncio.gather(
            *(h.broker.prepare() for _ in range(40)), return_exceptions=True
        )
        assert all(
            isinstance(value, LonoraError) and value.code == "broker_connection_timeout"
            for value in failures
        )
        assert len(h.created["rpc"]) == 1 and h.broker.rpc is None
        for _ in range(20):
            try:
                await h.broker.prepare()
            except LonoraError:
                pass
        assert len(h.created["rpc"]) == 1
        h.broker._slot("rpc").retry_at = 0
        recovered = await h.broker.prepare()
        assert recovered and len(h.created["rpc"]) == 2
        assert h.broker._slot("rpc").failures == 0
        print(
            "PASS synchronization timeout has singleflight bounded wait, cooldown blocks repeated failing traffic, and next allowed attempt recovers"
        )

        gate = asyncio.Event()
        await h.broker.invalidate("rpc", recovered)
        h.next_gate = gate
        waiting = asyncio.create_task(h.broker.prepare())
        await asyncio.sleep(0)
        # Historical REST must not require the blocked RPC synchronization or stream lease.
        with patch.object(MetatraderAccount, "get_historical_candles", AsyncMock(return_value=[])):
            assert await asyncio.wait_for(h.broker.candles("US500.cash", "1mn", 20), 0.2) == []
        assert not waiting.done()
        waiting.cancel()
        await asyncio.gather(waiting, return_exceptions=True)
        gate.set()
        await h.broker._slot("rpc").task
        print(
            "PASS blocked synchronization cannot block region-aware historical REST and consumer cancellation cannot cancel shared initialization"
        )

    storage = history_storage()
    with patch(
        "metaapi_cloud_sdk.metaapi.filesystem_history_database.FilesystemHistoryDatabase.load_history",
        AsyncMock(side_effect=PermissionError("cwd readonly")),
    ) as disk:
        await storage.initialize("fixture", "MetaApi")
        await storage.on_deal_added(
            "0",
            {"id": "1", "positionId": "2", "time": datetime.now(UTC), "entryType": "DEAL_ENTRY_IN"},
        )
        assert len(storage.deals) == 1
        await storage._flush_database()
        await storage.clear()
        assert not storage.deals
        disk.assert_not_awaited()
    print(
        "PASS official MemoryHistoryStorage works in read-only cwd with file cache disabled; live history indexing/flush/clear stay functional"
    )


if __name__ == "__main__":
    asyncio.run(main())
