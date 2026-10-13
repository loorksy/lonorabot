"""Explicit imported simulation candles for real PostgreSQL chart browser checks."""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from check_streaming import Fixture
from lonora_charts.runtime import refresh_chart


async def action(data: dict[str, Any]):
    fixture = await Fixture().open()
    try:
        if data["action"] == "init":
            # Use the real durable session already issued by Fixture.open. No second
            # password login is needed just to transfer the fixture to a browser.
            cookies = [
                {"name": cookie.name, "value": cookie.value}
                for cookie in fixture.client.cookies.jar
            ]
            connection = await fixture.request(
                "POST",
                "/trading/connections",
                {
                    "provider": "simulation",
                    "account_id": "chart-browser-" + uuid4().hex,
                    "enabled": True,
                },
            )
            symbol = "XAUUSD"
            candles = {
                symbol + ":" + frame: [
                    {
                        "symbol": symbol,
                        "timeframe": frame,
                        "time": (
                            datetime(2026, 10, 1, tzinfo=UTC) + timedelta(minutes=index * minutes)
                        ).isoformat(),
                        "open": str(100 + index),
                        "high": str(104 + index),
                        "low": str(99 + index),
                        "close": str(102 + index),
                    }
                    for index in range(60)
                ]
                for frame, minutes in (("1h", 60), ("15m", 15))
            }
            await fixture.request(
                "POST",
                f"/trading/connections/{connection['id']}/simulation",
                {
                    "snapshot": {
                        "balance": "10000",
                        "currency": "USD",
                        "candles": candles,
                        "instruments": [
                            {
                                "symbol": symbol,
                                "description": "Explicit imported fixture",
                                "digits": 2,
                                "tick_size": "0.01",
                                "volume_min": "0.01",
                                "volume_max": "100",
                                "volume_step": "0.01",
                            }
                        ],
                        "quotes": {
                            symbol: {
                                "symbol": symbol,
                                "bid": "160",
                                "ask": "161",
                                "observed_at": "2026-10-01T10:00:00+00:00",
                                "source": "simulation/imported-fixture",
                            }
                        },
                    }
                },
            )
            if data.get("empty"):
                return {
                    "account": connection["id"],
                    "chart": None,
                    "symbol": symbol,
                    "cookies": cookies,
                }
            chart = await fixture.request(
                "POST",
                "/charts",
                {
                    "payload": {
                        "account_id": connection["id"],
                        "symbol": symbol,
                        "timeframe": "15m",
                        "indicators": [{"name": "RSI", "period": 14}],
                        "annotations": [],
                    }
                },
            )
            data = {
                "account": connection["id"],
                "chart": chart["id"],
                "symbol": symbol,
                "cookies": cookies,
            }
            await refresh_chart(
                fixture.runtime.db,
                fixture.runtime.services(fixture.owner).brokers,
                fixture.owner,
                data["chart"],
                "explicit-browser-fixture",
                force=True,
            )
            return data
        if data["action"] == "refresh":
            await refresh_chart(
                fixture.runtime.db,
                fixture.runtime.services(fixture.owner).brokers,
                fixture.owner,
                data["chart"],
                "explicit-browser-fixture",
                force=True,
            )
            return await fixture.request("GET", f"/charts/{data['chart']}/scene")
        if data["action"] == "cleanup":
            if data.get("chart"):
                await fixture.request("DELETE", "/charts/" + data["chart"])
            await fixture.request("DELETE", "/trading/connections/" + data["account"])
            return {"cleaned": True}
        raise ValueError("Unknown chart browser fixture action")
    finally:
        await fixture.close()


if __name__ == "__main__":
    print(json.dumps(asyncio.run(action(json.load(sys.stdin)))))
