"""Seed an actual server-owned notification for both browser renderers."""

import asyncio
import json
import sys
from datetime import timedelta
from uuid import uuid4

from check_streaming import Fixture
from lonora_contracts.domain import AgentCreate, utcnow
from lonora_db.agents import agent_data, create_agent
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.schema import AttentionRow, RunRow, TradingJournalRow
from lonora_db.threads import conversation_thread
from lonora_gateway.attention import attention_tick
from lonora_gateway.liveness import Liveness
from lonora_gateway.watchdog import Watchdog


def cookies(fixture: Fixture) -> list[dict[str, str]]:
    return [
        {"name": cookie.name, "value": cookie.value or ""} for cookie in fixture.client.cookies.jar
    ]


async def critical_item(fixture: Fixture) -> str:
    """A fresh critical item in Lonora's conversation: work stopped after failures."""
    key = "browser-critical-" + uuid4().hex[:12]
    async with fixture.runtime.db.sessions() as session, session.begin():
        lonora = await ensure_personal_agent(session, fixture.owner)
        thread = await conversation_thread(session, fixture.owner, lonora.id)
        row = AttentionRow(
            owner_id=fixture.owner,
            agent_id=lonora.id,
            thread_id=thread.id,
            logical_key=key,
            coalesce_key=key,
            importance="critical",
            code="run_quarantined",
            due_at=utcnow(),
        )
        session.add(row)
        await session.flush()
        return row.id


async def main():
    fixture = await Fixture().open()
    try:
        critical = await critical_item(fixture)
        await attention_tick(
            fixture.runtime.db, fixture.runtime.services(fixture.owner).brokers, fixture.owner
        )
        if "--uncertain" not in sys.argv:
            notifications = (await fixture.client.get("/api/attention")).json()
            alert = next(row for row in notifications if row["id"] == critical)
            print(json.dumps({"notification": alert, "cookies": cookies(fixture)}))
            return
        # An operation still uncertain after the watchdog's threshold reaches the owner
        # once, in the conversation of the agent that placed it. The agent is created
        # directly (not cleaned up): its uncertain trade rightly refuses its deletion.
        async with fixture.runtime.db.sessions() as session, session.begin():
            desk = agent_data(
                await create_agent(
                    session, fixture.owner, AgentCreate(name="Gold desk " + uuid4().hex[:6])
                )
            )
            thread = await conversation_thread(session, fixture.owner, desk["id"])
            run = RunRow(thread_id=thread.id, agent_id=desk["id"], status="completed")
            session.add(run)
            await session.flush()
            session.add(
                TradingJournalRow(
                    operation_id="browser-" + uuid4().hex[:12],
                    owner_id=fixture.owner,
                    account_id="browser-account",
                    request_hash="h",
                    request={"symbol": "XAUUSD"},
                    status="ambiguous",
                    submitted_at=utcnow() - timedelta(hours=1),
                    result={"details": {"execution": {"agent_id": desk["id"], "run_id": run.id}}},
                )
            )
            # A plain update «تحديد الكل كمقروء» marks read (critical items stay unread, Q4).
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
        await Watchdog(fixture.runtime.db, Liveness(), set()).aging_operations()
        notifications = (await fixture.client.get("/api/attention")).json()
        alert = next(row for row in notifications if row["id"] == critical)
        uncertain = next(row for row in notifications if row["code"] == "operation_unresolved")
        informational = next(
            row
            for row in notifications
            if row["code"] == "internal_update" and row["agent_id"] == desk["id"]
        )
        print(
            json.dumps(
                {
                    "notification": alert,
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
