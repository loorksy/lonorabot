"""Browser-off real PostgreSQL stream publication and authoritative OHLC regressions."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_charts.runtime import publish_stream_update, refresh_chart
from lonora_charts.state import inspect_chart
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Candle, Quote
from lonora_core.user_error import LonoraError
from lonora_db.schema import EventRow, MarketWakeReceiptRow, MarketWatchRow
from lonora_market.candle_store import merge_candle, merge_history
from lonora_market.runtime import MarketRuntime
from lonora_market.watchers import check_watches
from sqlalchemy import func, select


async def wait_close(fixture: Fixture, chart_id: str, index: int, close: str) -> dict[str, Any]:
    for _ in range(300):
        data = await inspect_chart(fixture.runtime.db, fixture.owner, chart_id)
        if data["scene"] and data["scene"]["candles"][index]["close"] == close:
            return data["scene"]
        await asyncio.sleep(0.02)
    raise AssertionError("official broker candle did not reach the durable chart scene")


async def main() -> None:
    fixture = await Fixture().open()
    connection_id: str | None = None
    chart_ids: list[str] = []
    watch_id: str | None = None
    second: MarketRuntime | None = None
    try:
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": "live-" + uuid4().hex,
                "enabled": True,
            },
        )
        connection_id = str(connection["id"])
        pairs = [
            ("EURUSDm", "1m", 1),
            ("XAUUSD", "15m", 15),
            ("US100.cash", "4h", 240),
            ("BTCUSD", "1h", 60),
        ]
        imported: dict[str, list[dict[str, Any]]] = {
            symbol + ":" + timeframe: [
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "time": (
                        datetime(2026, 10, 1, tzinfo=UTC) + timedelta(minutes=i * minutes)
                    ).isoformat(),
                    "open": str(100 + i),
                    "high": str(104 + i),
                    "low": str(99 + i),
                    "close": str(102 + i),
                }
                for i in range(60)
            ]
            for symbol, timeframe, minutes in pairs
        }
        await fixture.request(
            "POST",
            f"/trading/connections/{connection_id}/simulation",
            {
                "snapshot": {"balance": "10000", "currency": "USD", "candles": imported},
            },
        )
        services = fixture.runtime.services(fixture.owner)
        market = services.market
        assert market.on_update is not None, "OwnerServices must bind the resident chart publisher"
        broker = await services.brokers.get(fixture.owner, connection_id)
        queues: dict[tuple[str, str], asyncio.Queue[Candle | Exception]] = {
            (symbol, timeframe): asyncio.Queue() for symbol, timeframe, _ in pairs
        }
        started: set[tuple[str, str]] = set()

        async def candle_stream(symbol: str, timeframe: str) -> AsyncIterator[Candle]:
            started.add((symbol, timeframe))
            while True:
                value = await queues[(symbol, timeframe)].get()
                if isinstance(value, Exception):
                    raise value
                yield value

        async def quote_stream(symbol: str) -> AsyncIterator[Quote]:
            await asyncio.Future()
            yield Quote(
                symbol=symbol,
                bid=Decimal("1"),
                ask=Decimal("1"),
                observed_at=utcnow(),
                source="unreachable",
            )

        history_calls = 0
        original_candles = broker.candles

        async def history(symbol: str, timeframe: str, limit: int) -> list[Candle]:
            nonlocal history_calls
            history_calls += 1
            return await original_candles(symbol, timeframe, limit)

        with (
            patch.object(broker, "stream_candles", candle_stream),
            patch.object(broker, "stream_quotes", quote_stream),
            patch.object(broker, "candles", history),
        ):
            for symbol, timeframe, _ in pairs:
                row = await fixture.request(
                    "POST",
                    "/charts",
                    {
                        "payload": {
                            "account_id": connection_id,
                            "symbol": symbol,
                            "timeframe": timeframe,
                            "indicators": [{"name": "sma", "period": 5}],
                            "annotations": [],
                        }
                    },
                )
                chart_ids.append(str(row["id"]))
                assert await refresh_chart(
                    fixture.runtime.db,
                    services.brokers,
                    fixture.owner,
                    chart_ids[-1],
                    "stream-fixture",
                    force=True,
                )
            agent = await fixture.agent("Live indicator watcher")
            thread = await fixture.conversation(agent)
            watch = await fixture.request(
                "POST",
                "/watches",
                {
                    "agent_id": agent["id"],
                    "thread_id": thread["id"],
                    "payload": {
                        "kind": "indicator",
                        "account_id": connection_id,
                        "symbol": pairs[0][0],
                        "timeframe": pairs[0][1],
                        "indicator": "sma",
                        "period": 5,
                        "series": "value",
                        "condition": "cross_above",
                        "level": "200",
                        "prompt": "Review the official streamed indicator crossing.",
                        "interval_seconds": 3600,
                    },
                },
            )
            watch_id = str(watch["id"])
            assert (
                await check_watches(fixture.runtime.db, services.brokers, owner_id=fixture.owner)
                == 0
            )
            await market.maintain()
            for _ in range(100):
                if len(started) == len(pairs):
                    break
                await asyncio.sleep(0.01)
            assert len(started) == len(pairs)
            baseline_calls = history_calls
            for chart_id, (symbol, timeframe, _) in zip(chart_ids, pairs, strict=True):
                current = Candle.model_validate(
                    {**imported[symbol + ":" + timeframe][-1], "high": "300", "close": "250"}
                )
                await queues[(symbol, timeframe)].put(current)
                scene = await wait_close(fixture, chart_id, -1, "250")
                assert scene["candles"][-1]["open"] == "159"
                assert (
                    scene["indicators"][0]["series"]["value"][-1]
                    == (157 + 158 + 159 + 160 + 250) / 5
                )
                assert scene["observation_source"] == "broker_candle_stream"
            assert history_calls == baseline_calls
            print(
                "PASS official live current bars and server indicators publish for Forex/metals/index/crypto without history per packet"
            )

            symbol, timeframe, _ = pairs[0]
            corrected = Candle.model_validate(
                {**imported[symbol + ":" + timeframe][56], "high": "400", "close": "350"}
            )
            await queues[(symbol, timeframe)].put(corrected)
            scene = await wait_close(fixture, chart_ids[0], 56, "350")
            assert (
                scene["indicators"][0]["series"]["value"][-1] == (157 + 350 + 159 + 160 + 250) / 5
            )
            async with fixture.runtime.db.sessions() as session:
                event = await session.scalar(
                    select(EventRow)
                    .where(
                        EventRow.owner_id == fixture.owner,
                        EventRow.kind == "cloud_charts.scene_updated",
                        EventRow.payload["id"].as_string() == chart_ids[0],
                    )
                    .order_by(EventRow.cursor.desc())
                )
                assert event and event.payload["scene_version"] == scene["scene_version"]
            print(
                "PASS corrected historical bar recalculates Python indicators and emits the matching durable scene event"
            )
            receipts: int | None = None
            for _ in range(100):
                async with fixture.runtime.db.sessions() as session:
                    watcher = await session.get(MarketWatchRow, watch_id)
                    receipts = await session.scalar(
                        select(func.count())
                        .select_from(MarketWakeReceiptRow)
                        .where(MarketWakeReceiptRow.payload["watch_id"].as_string() == watch_id)
                    )
                    if watcher and watcher.state.get("last_value") == str(
                        Decimal(str(scene["indicators"][0]["series"]["value"][-1]))
                    ):
                        break
                await asyncio.sleep(0.02)
            assert receipts == 1
            assert history_calls == baseline_calls
            assert (
                await check_watches(
                    fixture.runtime.db,
                    services.brokers,
                    candle_update=corrected,
                    connection_id=connection_id,
                    owner_id=fixture.owner,
                )
                == 0
            )
            print(
                "PASS corrected live indicator bypasses hourly polling and wakes once without REST or duplicate receipts"
            )

            # Duplicate packets are idempotent; account/version fences are enforced.
            async with fixture.runtime.db.sessions() as session, session.begin():
                assert not await merge_candle(
                    session,
                    fixture.owner,
                    connection_id,
                    corrected,
                    connection["version"],
                    market.identity,
                )
            second = MarketRuntime(fixture.runtime.db, services.brokers, fixture.owner)
            await second.maintain()
            assert not second.tasks and not second.candle_tasks
            try:
                async with fixture.runtime.db.sessions() as session, session.begin():
                    await merge_candle(
                        session,
                        fixture.owner,
                        connection_id,
                        corrected.model_copy(update={"close": Decimal("351")}),
                        connection["version"],
                        second.identity,
                    )
            except LonoraError as error:
                assert error.code == "market_stream_lease_lost"
            else:
                raise AssertionError("stale stream host wrote official OHLC")
            print(
                "PASS duplicate bars and competing resident account fences cannot publish duplicate or stale OHLC"
            )

            # History receives a stale current bar, while a live correction arrives during REST.
            original_render = __import__(
                "lonora_charts.runtime", fromlist=["render_scene"]
            ).render_scene
            ready, release = asyncio.Event(), asyncio.Event()

            async def delayed(*args: Any, **kwargs: Any) -> dict[str, Any]:
                result = await original_render(*args, **kwargs)
                ready.set()
                await release.wait()
                return result

            with patch("lonora_charts.runtime.render_scene", delayed):
                pending = asyncio.create_task(
                    refresh_chart(
                        fixture.runtime.db,
                        services.brokers,
                        fixture.owner,
                        chart_ids[0],
                        "delayed-history",
                        force=True,
                    )
                )
                await ready.wait()
                latest = Candle.model_validate(
                    {**imported[symbol + ":" + timeframe][-1], "high": "500", "close": "450"}
                )
                await queues[(symbol, timeframe)].put(latest)
                await wait_close(fixture, chart_ids[0], -1, "450")
                release.set()
                assert await pending
                await wait_close(fixture, chart_ids[0], -1, "450")
            print(
                "PASS streamed current OHLC remains authoritative when older historical refresh completes"
            )

            # Corrections during a REST window survive its eventual reconciliation.
            requested = utcnow()
            official = Candle.model_validate(
                {**imported[symbol + ":" + timeframe][55], "high": "450", "close": "400"}
            )
            async with fixture.runtime.db.sessions() as session, session.begin():
                await merge_candle(
                    session,
                    fixture.owner,
                    connection_id,
                    official,
                    connection["version"],
                    market.identity,
                )
            async with fixture.runtime.db.sessions() as session, session.begin():
                merged = await merge_history(
                    session,
                    fixture.owner,
                    connection_id,
                    symbol,
                    timeframe,
                    [Candle.model_validate(value) for value in imported[symbol + ":" + timeframe]],
                    500,
                    connection["version"],
                    requested,
                )
            assert merged[55].close == Decimal("400") and merged[-1].close == Decimal("450")
            assert (
                await publish_stream_update(
                    fixture.runtime.db,
                    fixture.owner,
                    connection_id,
                    symbol,
                    timeframe,
                    market.identity,
                )
                == 1
            )
            print(
                "PASS authoritative corrections arriving during REST survive historical reconciliation"
            )

            # No browser or active broker is needed to restore the persisted live scene.
            from lonora_api.runtime import ApiRuntime

            fresh = ApiRuntime.create(fixture.runtime.settings)
            try:
                restored = await inspect_chart(fresh.db, fixture.owner, chart_ids[0])
                assert restored["scene"]["candles"][55]["close"] == "400"
                assert not fresh.owners
            finally:
                await fresh.close()
            print("PASS browser-off stream scenes survive independent API restart")
            await queues[(symbol, timeframe)].put(RuntimeError("controlled SDK reconnect"))
            next_bar = latest.model_copy(
                update={
                    "time": latest.time + timedelta(minutes=1),
                    "open": Decimal("450"),
                    "high": Decimal("600"),
                    "low": Decimal("449"),
                    "close": Decimal("550"),
                }
            )
            await queues[(symbol, timeframe)].put(next_bar)
            resumed = await wait_close(fixture, chart_ids[0], -1, "550")
            assert len(resumed["candles"]) == 61
            assert resumed["candles"][-2]["close"] == "450"
            assert history_calls == baseline_calls
            try:
                async with fixture.runtime.db.sessions() as session, session.begin():
                    await merge_candle(
                        session,
                        fixture.owner,
                        connection_id,
                        next_bar.model_copy(update={"close": Decimal("551")}),
                        connection["version"] + 1,
                        market.identity,
                    )
            except LonoraError as error:
                assert error.code == "broker_configuration_changed"
            else:
                raise AssertionError("wrong configuration version wrote an official bar")
            assert (
                await publish_stream_update(
                    fixture.runtime.db,
                    fixture.owner,
                    connection_id,
                    symbol,
                    timeframe,
                    second.identity,
                )
                == 0
            )
            print(
                "PASS reconnect resumes official appended bars and rejects stale configuration or stream publishers"
            )
    finally:
        if second:
            await second.close()
        if connection_id:
            services = fixture.runtime.services(fixture.owner)
            await services.market.close()
        if watch_id:
            await fixture.request("DELETE", "/watches/" + watch_id)
        for chart_id in chart_ids:
            await fixture.request("DELETE", "/charts/" + chart_id)
        if connection_id:
            await fixture.request("DELETE", "/trading/connections/" + connection_id)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
