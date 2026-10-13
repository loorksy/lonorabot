"""Real PG/API chart/watch lifecycle with explicit imported simulation observations."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import Any
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapters.brokers.base import BrokerManager
from lonora_charts.runtime import chart_runtime_tick, refresh_chart
from lonora_contracts.chart import ChartState
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Quote
from lonora_core.user_error import LonoraError
from lonora_db.schema import (
    BrokerSessionRow,
    CloudChartRow,
    MarketWatchRow,
    TradingAccountRow,
)
from lonora_market.runtime import MarketRuntime
from lonora_market.watchers import check_watches


async def main() -> None:
    fixture = await Fixture().open()
    connection_id = None
    chart_id = None
    watch_id = None
    other_market = None
    try:
        agent = await fixture.agent("Resident market fixture")
        thread = await fixture.conversation(agent)
        symbol = "XAUUSDm"
        imported_quote = {
            "symbol": symbol,
            "bid": "2701",
            "ask": "2702",
            "source": "explicit-simulation-fixture",
            "observed_at": utcnow().isoformat(),
        }
        candles = [
            {
                "symbol": symbol,
                "timeframe": "1h",
                "time": (utcnow() - timedelta(hours=40 - i)).isoformat(),
                "open": str(2690 + i),
                "high": str(2692 + i),
                "low": str(2689 + i),
                "close": str(2691 + i),
            }
            for i in range(40)
        ]
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
        )
        connection_id = connection["id"]
        await fixture.request(
            "POST",
            f"/trading/connections/{connection_id}/simulation",
            {
                "snapshot": {
                    "balance": "10000",
                    "currency": "USD",
                    "quotes": {symbol: imported_quote},
                    "candles": {symbol + ":1h": candles},
                }
            },
        )
        chart = await fixture.request(
            "POST",
            "/charts",
            {
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "payload": {
                    "account_id": connection_id,
                    "symbol": symbol,
                    "timeframe": "1h",
                    "indicators": [{"name": "sma", "period": 5}],
                },
            },
        )
        chart_id = chart["id"]
        service = fixture.runtime.services(fixture.owner)
        # No browser, websocket, or model worker exists: call the actual gateway loop body.
        assert (
            await chart_runtime_tick(
                fixture.runtime.db, service.brokers, fixture.owner, "gateway-A"
            )
            == 1
        )
        await asyncio.sleep(0.15)
        scene = await fixture.request("GET", f"/charts/{chart_id}/scene")
        assert scene["symbol"] == symbol and scene["quote"]["source"] == imported_quote["source"]
        assert (
            scene["indicators"][0]["series"]["value"][-1]
            == sum(float(c["close"]) for c in candles[-5:]) / 5
        )
        async with fixture.runtime.db.sessions() as session:
            from lonora_db.schema import EventRow
            from sqlalchemy import select

            event = await session.scalar(
                select(EventRow).where(
                    EventRow.owner_id == fixture.owner, EventRow.kind == "market.quote_updated"
                )
            )
            assert event and event.payload["symbol"] == symbol
        print(
            "PASS browser-off gateway builds durable OHLC, exact symbol, quote timestamps and server indicators"
        )
        # A separately initialized API can read the saved scene without connecting a broker.
        from lonora_api.runtime import ApiRuntime
        from lonora_charts.state import inspect_chart

        fresh = ApiRuntime.create(fixture.runtime.settings)
        try:
            restored = await inspect_chart(fresh.db, fixture.owner, chart_id)
            assert restored["scene"] == scene and not fresh.owners
        finally:
            await fresh.close()
        print("PASS process restart restores chart evidence without a broker or browser request")
        other_market = MarketRuntime(fixture.runtime.db, service.brokers, fixture.owner)
        await other_market.synchronize({(connection_id, symbol)})
        assert not other_market.tasks and len(service.market.tasks) == 1
        print("PASS two runtime hosts cannot claim duplicate native streams for an active account")
        old_quote = Quote.model_validate(
            {
                **imported_quote,
                "bid": "2600",
                "ask": "2601",
                "observed_at": (utcnow() - timedelta(days=1)).isoformat(),
            }
        )
        await service.market.store(connection_id, symbol, "", old_quote.model_dump(mode="json"))
        assert (await service.market.quote(connection_id, symbol)).bid == Decimal("2701")
        print("PASS delayed broker packet cannot overwrite a newer durable observation")
        # Fence takeover during remote fetch rejects the old chart completion.
        from unittest.mock import patch

        import lonora_charts.runtime as chart_module

        ready, release = asyncio.Event(), asyncio.Event()
        original_render = chart_module.render_scene

        async def delayed(
            brokers: BrokerManager, owner_id: str, state: ChartState
        ) -> dict[str, Any]:
            ready.set()
            await release.wait()
            return await original_render(brokers, owner_id, state)

        with patch.object(chart_module, "render_scene", delayed):
            task = asyncio.create_task(
                refresh_chart(
                    fixture.runtime.db,
                    service.brokers,
                    fixture.owner,
                    chart_id,
                    "old-host",
                    force=True,
                )
            )
            await ready.wait()
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(CloudChartRow, chart_id, with_for_update=True)
                assert row is not None
                row.state = {
                    **row.state,
                    "runtime_owner": "new-host",
                    "runtime_fence": row.state["runtime_fence"] + 1,
                    "runtime_lease_until": None,
                }
            release.set()
            assert await task is False
        assert (await fixture.request("GET", f"/charts/{chart_id}/scene"))[
            "scene_version"
        ] == scene["scene_version"]
        print("PASS dead gateway fencing rejects delayed chart commits after lease takeover")
        watch = await fixture.request(
            "POST",
            "/watches",
            {
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "payload": {
                    "account_id": connection_id,
                    "symbol": symbol,
                    "condition": "above",
                    "level": "2700",
                    "prompt": "Explicit watch fixture",
                    "cooldown_seconds": 30,
                },
            },
        )
        watch_id = watch["id"]
        assert await check_watches(fixture.runtime.db, service.brokers) == 1
        assert await check_watches(fixture.runtime.db, service.brokers) == 0
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(MarketWatchRow, watch_id)
            assert row is not None
            assert row.state["last_triggered"] and row.state["last_value"] == "2701"
        print(
            "PASS persistent watch wakes an ordinary agent once from broker-runtime observations without browser timers"
        )
        # Price stream bypasses a future periodic deadline while preserving cooldown.
        async with fixture.runtime.db.sessions() as session, session.begin():
            watched = await session.get(MarketWatchRow, watch_id)
            assert watched is not None
            watched.payload = {**watched.payload, "condition": "cross_below", "level": "2700"}
            watched.version += 1
            watched.state = {
                "last_value": "2701",
                "next_check": (utcnow() + timedelta(minutes=10)).isoformat(),
            }
            account_row = await session.get(TradingAccountRow, connection_id)
            assert account_row is not None
            account_row.payload = {
                **account_row.payload,
                "quotes": {
                    symbol: {
                        **imported_quote,
                        "bid": "2690",
                        "ask": "2691",
                        "observed_at": utcnow().isoformat(),
                    }
                },
            }
        for _ in range(60):
            async with fixture.runtime.db.sessions() as session:
                watched = await session.get(MarketWatchRow, watch_id)
                assert watched is not None
                if watched.state.get("last_triggered"):
                    break
            await asyncio.sleep(0.05)
        assert watched.state.get("last_triggered") and watched.state["last_value"] == "2690"
        print("PASS native quote delivery wakes crossing watch before its periodic deadline")
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(BrokerSessionRow, connection_id, with_for_update=True)
            assert row is not None
            row.payload = {**row.payload, "enabled": False}
            row.version += 1
        await service.market.synchronize({(connection_id, symbol)})
        assert not service.market.tasks
        try:
            await service.market.quote(connection_id, symbol)
            raise AssertionError("Disabled broker served cached quote")
        except LonoraError as error:
            assert error.code == "broker_disabled"
        print("PASS disabling a connection cancels streams and blocks cached market reads")
    finally:
        if other_market:
            await other_market.close()
        if watch_id:
            await fixture.request("DELETE", "/watches/" + watch_id)
        if chart_id:
            await fixture.request("DELETE", "/charts/" + chart_id)
        if connection_id:
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(TradingAccountRow, connection_id)
                if row:
                    await session.delete(row)
            await fixture.request("DELETE", "/trading/connections/" + connection_id)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
