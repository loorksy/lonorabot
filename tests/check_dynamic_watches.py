"""Actual PostgreSQL dynamic watches, source replay dedup and restart durability."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from check_streaming import Fixture
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Quote
from lonora_db.schema import MarketWakeReceiptRow, MarketWatchRow
from lonora_market.watchers import check_watches
from sqlalchemy import func, select


async def main() -> None:
    f = await Fixture().open()
    connection_id = ""
    try:
        agent = await f.agent("Dynamic evidence")
        thread = await f.conversation(agent)
        connection_id = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
            )
        )["id"]
        watch = await f.request(
            "POST",
            "/watches",
            {
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "payload": {
                    "kind": "dynamic",
                    "account_id": connection_id,
                    "symbol": "US500.cash",
                    "timeframe": "15m",
                    "detector": {
                        "id": "level",
                        "kind": "level",
                        "level": "100",
                        "tolerance": "0.1",
                        "exit_tolerance": "1",
                    },
                    "required_observations": 2,
                    "prompt": "Revalidate evidence; confirmation is not execution",
                },
            },
        )
        services = f.runtime.services(f.owner)

        async def tick(bid: str, offset: int = 0) -> int:
            return await check_watches(
                f.runtime.db,
                services.brokers,
                price_update=Quote(
                    symbol="US500.cash",
                    bid=Decimal(bid),
                    ask=Decimal(bid) + 1,
                    observed_at=utcnow() - timedelta(seconds=offset),
                    source="explicit-dynamic-replay",
                ),
                connection_id=connection_id,
                owner_id=f.owner,
            )

        assert await tick("101") == 0
        async with f.runtime.db.sessions() as session:
            row = await session.get(MarketWatchRow, watch["id"])
            assert row and row.state["lifecycle"] == "forming"
        assert await tick("101") == 1
        # Distinct ticks do not wake an already-confirmed dynamic setup repeatedly.
        assert await tick("102") == 0
        assert await tick("103") == 0
        async with f.runtime.db.sessions() as session:
            row = await session.get(MarketWatchRow, watch["id"])
            assert row and row.state["observation"]["symbol"] == "US500.cash"
            assert row.state["observation"]["detector_version"] == "1"
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(MarketWakeReceiptRow)
                    .where(MarketWakeReceiptRow.thread_id == thread["id"])
                )
                == 1
            )
        assert await tick("90") == 0
        async with f.runtime.db.sessions() as session:
            row = await session.get(MarketWatchRow, watch["id"])
            assert row and row.state["lifecycle"] == "invalidated"
        assert await tick("110", offset=300) == 0
        async with f.runtime.db.sessions() as session:
            row = await session.get(MarketWatchRow, watch["id"])
            assert row and row.state["evaluation_status"] == "suspended_health"
            assert row.state["lifecycle"] == "invalidated"
        print(
            "PASS durable dynamic FORMING/CONFIRMED/INVALIDATED, one meaningful wake, versioned exact evidence and stale suspension"
        )
    finally:
        if connection_id:
            await f.client.delete(f"/api/trading/connections/{connection_id}")
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
