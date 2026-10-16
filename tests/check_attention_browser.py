"""Seed an actual server-owned notification for both browser renderers."""

import asyncio
import json

from check_streaming import Fixture
from lonora_gateway.attention import attention_tick


async def main():
    fixture = await Fixture().open()
    try:
        await fixture.request(
            "PUT", "/trading/controls", {"enabled": False, "emergency_stop": True}
        )
        await attention_tick(
            fixture.runtime.db, fixture.runtime.services(fixture.owner).brokers, fixture.owner
        )
        notifications = (await fixture.client.get("/api/attention")).json()
        alert = next(row for row in notifications if row["code"] == "emergency_stop")
        print(
            json.dumps(
                {
                    "notification": alert,
                    "cookies": [
                        {"name": cookie.name, "value": cookie.value}
                        for cookie in fixture.client.cookies.jar
                    ],
                }
            )
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
