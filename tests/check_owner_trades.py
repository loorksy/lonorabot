"""The trades page's buttons on the server (trades.page, Q30): the owner's own buy, modify
and close go through POST /api/trading/execute, the single executor, and each is confirmed
from the broker. Run on a disposable *_test database.
"""

import asyncio
import json
import sys
from typing import Any
from uuid import uuid4

from agent_pages_browser import SYMBOL, snapshot
from check_streaming import Fixture


async def execute(fixture: Fixture, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    response = await fixture.client.post(
        "/api/trading/execute", json={"operation_id": str(uuid4()), "symbol": SYMBOL, **body}
    )
    return response.status_code, response.json()


async def main() -> None:
    fixture = await Fixture().open()
    account = None
    try:
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": "owner-trades-" + uuid4().hex,
                "enabled": True,
            },
        )
        account = connection["id"]
        await fixture.request(
            "POST", f"/trading/connections/{account}/simulation", {"snapshot": snapshot()}
        )
        status, opened = await execute(
            fixture, {"account_id": account, "action": "buy", "volume": "0.2", "stop_loss": "200"}
        )
        assert status == 200 and opened["status"] == "confirmed", opened
        positions = (await fixture.request("GET", f"/trading/accounts/{account}"))["positions"]
        assert len(positions) == 1, positions
        position = positions[0]["id"]
        print("PASS the owner's buy opens one position through the executor")

        status, tightened = await execute(
            fixture,
            {
                "account_id": account,
                "action": "modify_position",
                "position_id": position,
                "stop_loss": "205",
            },
        )
        assert status == 200 and tightened["status"] == "confirmed", tightened
        print("PASS the owner's stop moved toward the market is confirmed")

        status, closed = await execute(
            fixture, {"account_id": account, "action": "close_position", "position_id": position}
        )
        assert status == 200 and closed["status"] == "confirmed", closed
        assert not (await fixture.request("GET", f"/trading/accounts/{account}"))["positions"]
        print("PASS the owner's close is confirmed and the position is gone")
    finally:
        if account:
            await fixture.client.delete(f"/api/trading/connections/{account}")
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
    json.dump({"passed": True}, sys.stdout)
