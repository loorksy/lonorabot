"""Seed real server-owned attention for both browser renderers of the attention view.

An agent's operation becomes ambiguous through the real projection, which raises its
Settle card and the owner's "operation_uncertain" item in that agent's conversation;
a plain update the view never lists sits beside it.
"""

import asyncio
import json
from datetime import timedelta
from uuid import uuid4

from check_streaming import Fixture
from lonora_contracts.domain import AgentCreate, utcnow
from lonora_db.agents import agent_data, create_agent
from lonora_db.events import emit
from lonora_db.schema import AttentionRow, TradingJournalRow
from lonora_db.threads import conversation_thread
from lonora_gateway.attention import attention_tick


def cookies(fixture: Fixture) -> list[dict[str, str]]:
    return [
        {"name": cookie.name, "value": cookie.value or ""} for cookie in fixture.client.cookies.jar
    ]


async def main():
    fixture = await Fixture().open()
    try:
        # The agent is created directly (not cleaned up): its uncertain trade rightly
        # refuses its deletion.
        async with fixture.runtime.db.sessions() as session, session.begin():
            desk = agent_data(
                await create_agent(
                    session, fixture.owner, AgentCreate(name="Gold desk " + uuid4().hex[:6])
                )
            )
            thread = await conversation_thread(session, fixture.owner, desk["id"])
            operation_id = "browser-" + uuid4().hex[:12]
            session.add(
                TradingJournalRow(
                    operation_id=operation_id,
                    owner_id=fixture.owner,
                    account_id="browser-account",
                    request_hash="h",
                    request={"symbol": "XAUUSD"},
                    status="ambiguous",
                    submitted_at=utcnow() - timedelta(hours=1),
                )
            )
            await session.flush()
            emit(
                session,
                fixture.owner,
                "trading.operation_updated",
                agent_id=desk["id"],
                thread_id=thread.id,
                payload={"operation_id": operation_id, "status": "ambiguous"},
            )
            # A plain update: an attention item the view never lists.
            info_key = "browser-info-" + uuid4().hex[:12]
            session.add(
                AttentionRow(
                    owner_id=fixture.owner,
                    agent_id=desk["id"],
                    thread_id=thread.id,
                    logical_key=info_key,
                    coalesce_key=info_key,
                    importance="important_change",
                    code="internal_update",
                    due_at=utcnow(),
                )
            )
        await attention_tick(
            fixture.runtime.db, fixture.runtime.services(fixture.owner).brokers, fixture.owner
        )
        notifications = (await fixture.client.get("/api/attention")).json()
        uncertain = next(
            row
            for row in notifications
            if row["code"] == "operation_uncertain"
            and row["parameters"].get("operation_id") == operation_id
        )
        informational = next(
            row
            for row in notifications
            if row["code"] == "internal_update" and row["agent_id"] == desk["id"]
        )
        print(
            json.dumps(
                {
                    "uncertain": uncertain,
                    "informational": informational,
                    "agent": {"id": desk["id"], "name": desk["name"]},
                    "cookies": cookies(fixture),
                }
            )
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
