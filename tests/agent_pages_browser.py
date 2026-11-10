"""Real PostgreSQL fixture for the phase 4a agent pages (tests/web/agent-pages.spec.mjs).

A simulation account with imported candles, a trading agent on XAUUSD, a research agent,
a group with a purpose and a lead, and one open position the owner opened through the
executor. Cleanup removes them through the API (the UI itself never deletes an agent or a
group) and restores the trading controls as they were.
"""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from check_streaming import Fixture
from lonora_gateway.attention import attention_tick

SYMBOL = "XAUUSD"


def snapshot() -> dict[str, Any]:
    """A simulation account with 15m candles and a fresh quote (the executor refuses a stale one)."""
    start = datetime.now(UTC).replace(second=0, microsecond=0) - timedelta(minutes=15 * 60)
    return {
        "balance": "10000",
        "currency": "USD",
        "candles": {
            f"{SYMBOL}:15m": [
                {
                    "symbol": SYMBOL,
                    "timeframe": "15m",
                    "time": (start + timedelta(minutes=15 * index)).isoformat(),
                    "open": str(150 + index),
                    "high": str(154 + index),
                    "low": str(149 + index),
                    "close": str(152 + index),
                }
                for index in range(60)
            ]
        },
        "instruments": [
            {
                "symbol": SYMBOL,
                "description": "Explicit imported fixture",
                "digits": 2,
                "tick_size": "0.01",
                "volume_min": "0.01",
                "volume_max": "100",
                "volume_step": "0.01",
            }
        ],
        "quotes": {
            SYMBOL: {
                "symbol": SYMBOL,
                "bid": "210",
                "ask": "211",
                "observed_at": datetime.now(UTC).isoformat(),
                "source": "simulation/imported-fixture",
            }
        },
    }


def cookies(fixture: Fixture) -> list[dict[str, str]]:
    return [{"name": cookie.name, "value": cookie.value} for cookie in fixture.client.cookies.jar]


async def action(data: dict[str, Any]) -> dict[str, Any]:
    if data["action"] == "init":
        fixture = await Fixture().open()
        try:
            tag = uuid4().hex[:6]
            connection = await fixture.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": "agent-pages-" + tag, "enabled": True},
            )
            await fixture.request(
                "POST",
                f"/trading/connections/{connection['id']}/simulation",
                {"snapshot": snapshot()},
            )
            chart = {"account": connection["id"], "symbol": SYMBOL}
            trader = await fixture.request(
                "POST",
                "/agents/create",
                {
                    "template": "trading",
                    "name": f"Gold desk {tag}",
                    "responsibility": "Follows gold",
                    "market": chart["symbol"],
                    "account_id": chart["account"],
                },
            )
            research = await fixture.request(
                "POST",
                "/agents/create",
                {"template": "research", "name": f"Reader {tag}", "responsibility": "Reads"},
            )
            group = await fixture.request(
                "POST",
                "/groups/create",
                {
                    "name": f"Desk {tag}",
                    "member_ids": [trader["id"], research["id"]],
                    "participation": "mentions_or_lead",
                    "purpose": "Gold research",
                    "lead_agent_id": research["id"],
                },
            )
            controls = await fixture.request("GET", "/trading/controls")
            await fixture.request(
                "PUT", "/trading/controls", {"enabled": True, "emergency_stop": False}
            )
            opened = await fixture.request(
                "POST",
                "/trading/execute",
                {
                    "account_id": chart["account"],
                    "operation_id": str(uuid4()),
                    "action": "buy",
                    "symbol": chart["symbol"],
                    "volume": "0.1",
                    "stop_loss": "200",
                },
            )
            assert opened["status"] == "confirmed", opened
            return {
                "cookies": cookies(fixture),
                "account": chart["account"],
                "symbol": chart["symbol"],
                "trader": trader,
                "research": research,
                "group": group,
                "controls": controls,
            }
        finally:
            await fixture.close(cleanup=False)
    if data["action"] == "cleanup":
        fixture = await Fixture().open()
        try:
            for group in data.get("groups", []) + [data["group"]["id"]]:
                await fixture.client.delete(f"/api/groups/{group}")
            for agent in (data["trader"]["id"], data["research"]["id"]):
                await fixture.client.delete(f"/api/agents/{agent}")
            await fixture.request("PUT", "/trading/controls", data["controls"])
            await fixture.client.delete(f"/api/trading/connections/{data['account']}")
            # The brake toggled for the owner's position raised attention; settle it so the
            # next spec starts from the controls' own state.
            await attention_tick(
                fixture.runtime.db, fixture.runtime.services(fixture.owner).brokers, fixture.owner
            )
        finally:
            await fixture.close(cleanup=False)
        return {"cleaned": True}
    raise ValueError("Unknown agent pages fixture action")


if __name__ == "__main__":
    print(json.dumps(asyncio.run(action(json.load(sys.stdin)))))
