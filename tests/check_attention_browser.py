"""Seed an actual server-owned notification for both browser renderers."""

import asyncio
import json
import sys
from datetime import timedelta
from uuid import uuid4

from check_streaming import Fixture
from lonora_contracts.domain import utcnow
from lonora_db.schema import TradingJournalRow
from lonora_gateway.attention import attention_tick
from lonora_gateway.liveness import Liveness
from lonora_gateway.watchdog import Watchdog


def cookies(fixture: Fixture) -> list[dict[str, str]]:
    return [
        {"name": cookie.name, "value": cookie.value or ""} for cookie in fixture.client.cookies.jar
    ]


async def main():
    fixture = await Fixture().open()
    try:
        await fixture.request(
            "PUT", "/trading/controls", {"enabled": False, "emergency_stop": True}
        )
        await attention_tick(
            fixture.runtime.db, fixture.runtime.services(fixture.owner).brokers, fixture.owner
        )
        if "--uncertain" not in sys.argv:
            notifications = (await fixture.client.get("/api/attention")).json()
            alert = next(row for row in notifications if row["code"] == "emergency_stop")
            print(json.dumps({"notification": alert, "cookies": cookies(fixture)}))
            return
        # An operation still uncertain after the watchdog's threshold reaches the owner once.
        async with fixture.runtime.db.sessions() as session, session.begin():
            session.add(
                TradingJournalRow(
                    operation_id="browser-" + uuid4().hex[:12],
                    owner_id=fixture.owner,
                    account_id="browser-account",
                    request_hash="h",
                    request={"symbol": "XAUUSD"},
                    status="ambiguous",
                    submitted_at=utcnow() - timedelta(hours=1),
                    result={},
                )
            )
        await Watchdog(fixture.runtime.db, Liveness(), set()).aging_operations()
        notifications = (await fixture.client.get("/api/attention")).json()
        alert = next(row for row in notifications if row["code"] == "emergency_stop")
        uncertain = next(row for row in notifications if row["code"] == "operation_unresolved")
        print(
            json.dumps(
                {
                    "notification": alert,
                    "uncertain": uncertain,
                    "cookies": cookies(fixture),
                }
            )
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
