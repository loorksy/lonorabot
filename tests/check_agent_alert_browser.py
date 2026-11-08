"""Seed an Agent's own owner alert (owner_notify) for the browser renderers."""

import asyncio
import json
from uuid import uuid4

from check_streaming import Fixture
from lonora_contracts.attention import OwnerNotifyRequest
from lonora_db.attention import notify_owner
from lonora_db.threads import conversation_thread


async def main() -> None:
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Gold desk")
        async with fixture.runtime.db.sessions() as session, session.begin():
            thread = await conversation_thread(session, fixture.owner, agent["id"])
            result = await notify_owner(
                session,
                fixture.owner,
                agent["id"],
                thread.id,
                OwnerNotifyRequest(
                    importance="critical",
                    summary="أُغلقت صفقة XAUUSD عند وقف الخسارة 2310.5",
                    evidence_refs=["broker:sim-gold-1"],
                    dedupe_key="browser-" + uuid4().hex,
                ),
            )
        print(
            json.dumps(
                {
                    "notification": result["attention"],
                    "agent": agent,
                    "cookies": [
                        {"name": cookie.name, "value": cookie.value}
                        for cookie in fixture.client.cookies.jar
                    ],
                }
            )
        )
    finally:
        # The alert belongs to the Agent: keep both for the browser that reads them.
        await fixture.close(cleanup=False)


if __name__ == "__main__":
    asyncio.run(main())
