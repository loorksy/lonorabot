"""Real database watch suspension/recovery using only explicit simulation prices."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from check_streaming import Fixture
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Candle, Quote
from lonora_db.schema import EventRow, MarketWakeReceiptRow, MarketWatchRow, TradingAccountRow
from lonora_market.watchers import check_watches
from sqlalchemy import func, select


async def main() -> None:
    fixture = await Fixture().open()
    watch_id = connection_id = indicator_watch_id = None
    try:
        agent = await fixture.agent("Health recovery fixture")
        thread = await fixture.conversation(agent)
        symbol = "US500.cash"
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
        )
        connection_id = connection["id"]
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
                    "level": "5000",
                    "prompt": "Check fresh market evidence only",
                    "cooldown_seconds": 30,
                },
            },
        )
        watch_id = watch["id"]
        brokers = fixture.runtime.services(fixture.owner).brokers
        stale = Quote(
            symbol=symbol,
            bid=Decimal("5100"),
            ask=Decimal("5101"),
            observed_at=utcnow() - timedelta(minutes=5),
            source="scripted-simulation",
        )
        # Stream delivery cannot turn old source data into a new confirmation.
        for _ in range(3):
            assert (
                await check_watches(
                    fixture.runtime.db,
                    brokers,
                    price_update=stale,
                    owner_id=fixture.owner,
                    connection_id=connection_id,
                )
                == 0
            )
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(MarketWatchRow, watch_id)
            assert row and row.state["evaluation_status"] == "suspended_health"
            assert row.state["code"] == "market_quote_stale"
            events = list(
                (
                    await session.scalars(
                        select(EventRow).where(
                            EventRow.owner_id == fixture.owner,
                            EventRow.kind == "watch.suspended_health",
                        )
                    )
                ).all()
            )
            assert (
                len([event for event in events if event.payload.get("watch_id") == watch_id]) == 1
            )
            receipts = await session.scalar(
                select(func.count())
                .select_from(MarketWakeReceiptRow)
                .where(MarketWakeReceiptRow.thread_id == thread["id"])
            )
            assert receipts == 0
        print(
            "PASS repeated stale stream packets suspend durable watch once without wake or model call"
        )
        fresh = stale.model_copy(update={"observed_at": utcnow()})
        assert (
            await check_watches(
                fixture.runtime.db,
                brokers,
                price_update=fresh,
                owner_id=fixture.owner,
                connection_id=connection_id,
            )
            == 1
        )
        assert (
            await check_watches(
                fixture.runtime.db,
                brokers,
                price_update=fresh,
                owner_id=fixture.owner,
                connection_id=connection_id,
            )
            == 0
        )
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(MarketWatchRow, watch_id)
            assert row and row.state["evaluation_status"] == "active"
            assert row.state["health"]["state"] == "healthy" and "code" not in row.state
            events = list(
                (
                    await session.scalars(
                        select(EventRow).where(
                            EventRow.owner_id == fixture.owner,
                            EventRow.kind == "watch.resumed_health",
                        )
                    )
                ).all()
            )
            assert (
                len([event for event in events if event.payload.get("watch_id") == watch_id]) == 1
            )
            receipts = await session.scalar(
                select(func.count())
                .select_from(MarketWakeReceiptRow)
                .where(MarketWakeReceiptRow.thread_id == thread["id"])
            )
            assert receipts == 1
        print(
            "PASS recovery re-evaluates fresh source once, preserving exact broker symbol and durable dedup"
        )
        # The durable state is accessible without the originating process, browser or broker.
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(MarketWatchRow, watch_id)
            assert row and row.state["health"]["symbol"] == symbol
            assert row.state["last_triggered"]
        print("PASS new database session restores health and receipt state without browser context")
        indicator = await fixture.request(
            "POST",
            "/watches",
            {
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "payload": {
                    "kind": "indicator",
                    "account_id": connection_id,
                    "symbol": symbol,
                    "timeframe": "1m",
                    "indicator": "sma",
                    "period": 2,
                    "condition": "above",
                    "level": "5",
                    "prompt": "Only trust fresh indicator inputs",
                },
            },
        )
        indicator_watch_id = indicator["id"]
        old_candles = [
            Candle(
                symbol=symbol,
                timeframe="1m",
                time=utcnow() - timedelta(minutes=10 - i),
                open=Decimal(10),
                high=Decimal(12),
                low=Decimal(9),
                close=Decimal(11),
            )
            for i in range(3)
        ]
        market = fixture.runtime.services(fixture.owner).market
        await market.store(
            connection_id,
            symbol,
            "1m",
            {"candles": [bar.model_dump(mode="json") for bar in old_candles]},
        )
        assert (
            await check_watches(
                fixture.runtime.db,
                brokers,
                candle_update=old_candles[-1],
                owner_id=fixture.owner,
                connection_id=connection_id,
            )
            == 0
        )
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(MarketWatchRow, indicator_watch_id)
            assert row and row.state["code"] == "market_candles_stale"
        fresh_candles = [
            bar.model_copy(update={"time": utcnow() - timedelta(minutes=2 - i)})
            for i, bar in enumerate(old_candles)
        ]
        await market.store(
            connection_id,
            symbol,
            "1m",
            {"candles": [bar.model_dump(mode="json") for bar in fresh_candles]},
        )
        assert (
            await check_watches(
                fixture.runtime.db,
                brokers,
                candle_update=fresh_candles[-1],
                owner_id=fixture.owner,
                connection_id=connection_id,
            )
            == 1
        )
        assert (
            await check_watches(
                fixture.runtime.db,
                brokers,
                candle_update=fresh_candles[-1],
                owner_id=fixture.owner,
                connection_id=connection_id,
            )
            == 0
        )
        print(
            "PASS newly received stale candle cache cannot confirm indicator; fresh source resumes once"
        )

    finally:
        if indicator_watch_id:
            await fixture.request("DELETE", "/watches/" + indicator_watch_id)
        if watch_id:
            await fixture.request("DELETE", "/watches/" + watch_id)
        if connection_id:
            async with fixture.runtime.db.sessions() as session, session.begin():
                account = await session.get(TradingAccountRow, connection_id)
                if account:
                    await session.delete(account)
            await fixture.request("DELETE", "/trading/connections/" + connection_id)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
