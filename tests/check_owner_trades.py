"""The trades page's buttons on the server (trades.page, Q30): the owner's own modify and
close go through POST /api/trading/execute, the single executor, under the global brake.

With Trading OFF a close is still admitted (an exit), a stop moved toward the market is
admitted (it only bounds the loss), and a stop moved away from the market is refused by
the server: the page never relies on hiding a button. Run on a disposable *_test database.
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
    controls = await fixture.request("GET", "/trading/controls")
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
        await fixture.request(
            "PUT", "/trading/controls", {"enabled": True, "emergency_stop": False}
        )
        status, opened = await execute(
            fixture, {"account_id": account, "action": "buy", "volume": "0.2", "stop_loss": "200"}
        )
        assert status == 200 and opened["status"] == "confirmed", opened
        positions = (await fixture.request("GET", f"/trading/accounts/{account}"))["positions"]
        assert len(positions) == 1, positions
        position = positions[0]["id"]
        print("PASS the owner's buy opens one position through the executor")

        # Trading OFF: the owner's «إيقاف التداول الجديد».
        await fixture.request(
            "PUT", "/trading/controls", {"enabled": False, "emergency_stop": True}
        )
        status, widened = await execute(
            fixture,
            {
                "account_id": account,
                "action": "modify_position",
                "position_id": position,
                "stop_loss": "190",
            },
        )
        assert status >= 400 or widened.get("status") == "failed", widened
        after = (await fixture.request("GET", f"/trading/accounts/{account}"))["positions"]
        assert after[0]["stop_loss"] in {"200", "200.00", "200.0"}, after
        print("PASS with Trading OFF the server refuses a stop moved away from the market")

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
        print("PASS with Trading OFF a stop moved toward the market is admitted")

        status, closed = await execute(
            fixture, {"account_id": account, "action": "close_position", "position_id": position}
        )
        assert status == 200 and closed["status"] == "confirmed", closed
        assert not (await fixture.request("GET", f"/trading/accounts/{account}"))["positions"]
        print("PASS with Trading OFF the owner's close is admitted and the position is gone")
    finally:
        await fixture.request("PUT", "/trading/controls", controls)
        if account:
            await fixture.client.delete(f"/api/trading/connections/{account}")
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
    json.dump({"passed": True}, sys.stdout)
