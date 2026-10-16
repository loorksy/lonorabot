"""PostgreSQL watch processing never renews delayed quote/candle evidence."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Candle, Quote
from lonora_db.schema import MarketWatchRow
from lonora_market.watchers import check_watches


async def main() -> None:
    f = await Fixture().open()
    connection_id = ""
    try:
        agent = await f.agent("Source-time expiry")
        thread = await f.conversation(agent)
        connection_id = (
            await f.request(
                "POST",
                "/trading/connections",
                {
                    "provider": "simulation",
                    "account_id": uuid4().hex,
                    "enabled": True,
                },
            )
        )["id"]
        services = f.runtime.services(f.owner)
        evidence_time = utcnow() - timedelta(seconds=20)
        configs = [
            ("EURUSDm", "1m", {"id": "level", "kind": "level", "level": "100"}),
            ("BTCUSDm", "1m", {"id": "doji", "kind": "candle", "pattern": "doji"}),
        ]
        for symbol, timeframe, detector in configs:
            watch = await f.request(
                "POST",
                "/watches",
                {
                    "agent_id": agent["id"],
                    "thread_id": thread["id"],
                    "payload": {
                        "kind": "dynamic",
                        "account_id": connection_id,
                        "symbol": symbol,
                        "timeframe": timeframe,
                        "detector": detector,
                        "confirmation_ttl_seconds": 5,
                        "prompt": "Inspect source evidence",
                    },
                },
            )
            quote = Quote(
                symbol=symbol,
                bid=Decimal(101),
                ask=Decimal(102),
                observed_at=evidence_time,
                source="broker-delayed",
            )
            candle = Candle(
                symbol=symbol,
                timeframe=timeframe,
                time=evidence_time - timedelta(minutes=1),
                open=Decimal(100),
                high=Decimal(102),
                low=Decimal(98),
                close=Decimal(100),
            )
            market = AsyncMock()
            market.quote.return_value = quote
            market.candles.return_value = [candle]
            with patch("lonora_market.watchers.broker_market", return_value=market):
                assert await check_watches(f.runtime.db, services.brokers, owner_id=f.owner) == 0
            async with f.runtime.db.sessions() as session:
                row = await session.get(MarketWatchRow, watch["id"])
                assert row and row.state["lifecycle"] == "expired"
                assert row.state["lifecycle_reason"] == "watch_confirmation_expired"
                expiry = row.state["confirmation_valid_until"]
                assert expiry == (evidence_time + timedelta(seconds=5)).isoformat()
                assert (
                    datetime.fromisoformat(row.state["observation"]["observed_at"]) == evidence_time
                )
            # The next invocation reloads all state from PostgreSQL. An expired
            # watch stays expired even if a newer source packet is available.
            market.quote.return_value = quote.model_copy(update={"observed_at": utcnow()})
            with patch("lonora_market.watchers.broker_market", return_value=market):
                assert await check_watches(f.runtime.db, services.brokers, owner_id=f.owner) == 0
            async with f.runtime.db.sessions() as session:
                row = await session.get(MarketWatchRow, watch["id"])
                assert row and row.state["confirmation_valid_until"] == expiry
        print(
            "PASS delayed quote/candle source TTL, no stale wake, PostgreSQL restart/replay expiry"
        )
    finally:
        if connection_id:
            await f.client.delete(f"/api/trading/connections/{connection_id}")
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
