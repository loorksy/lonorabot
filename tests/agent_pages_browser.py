"""Real PostgreSQL fixture for the phase 4a agent pages (tests/web/agent-pages.spec.mjs).

A simulation account with imported candles, a trading agent on XAUUSD, a research agent,
a group with a purpose and a lead, and one open position the owner opened through the
executor. Cleanup removes them through the API (the UI itself never deletes an agent or a
group) and restores the trading controls as they were.
"""

import asyncio
import json
import sys
from typing import Any
from uuid import uuid4

from check_chart_browser import action as chart_fixture
from check_streaming import Fixture


def cookies(fixture: Fixture) -> list[dict[str, str]]:
    return [{"name": cookie.name, "value": cookie.value} for cookie in fixture.client.cookies.jar]


async def action(data: dict[str, Any]) -> dict[str, Any]:
    if data["action"] == "init":
        chart = await chart_fixture({"action": "init", "empty": True})
        fixture = await Fixture().open()
        try:
            tag = uuid4().hex[:6]
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
                    "stop_loss": "150",
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
        finally:
            await fixture.close(cleanup=False)
        await chart_fixture({"action": "cleanup", "account": data["account"]})
        return {"cleaned": True}
    raise ValueError("Unknown agent pages fixture action")


if __name__ == "__main__":
    print(json.dumps(asyncio.run(action(json.load(sys.stdin)))))
