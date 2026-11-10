"""Seed real conversations for the chat-list browser specs (tests/web/chat-lists.spec.mjs).

``init`` creates agents with canonical conversations and a group, then writes messages
straight into their history: unread agent answers, an owner message the server accepted
(one grey tick) and one whose run started (two accent ticks). ``message`` adds an agent
answer and publishes ``message.created`` (the heads-up); ``attention`` raises a fresh
critical item (new trading stopped) and ``restore`` puts the trading controls back as the
spec found them. Agents are kept: the browser uses them after this process exits.
"""

import asyncio
import json
import sys
from typing import Any
from uuid import uuid4

from check_streaming import Fixture
from lonora_db.events import emit
from lonora_db.messages import message_data
from lonora_db.schema import MessageRow, RunRow, ThreadRow
from lonora_gateway.attention import attention_tick


def cookies(fixture: Fixture) -> list[dict[str, str]]:
    return [
        {"name": cookie.name, "value": cookie.value or ""} for cookie in fixture.client.cookies.jar
    ]


async def add(
    fixture: Fixture, thread_id: str, role: str, agent_id: str | None, content: str, live: bool
) -> dict[str, Any]:
    async with fixture.runtime.db.sessions() as session, session.begin():
        thread = await session.get(ThreadRow, thread_id, with_for_update=True)
        assert thread is not None
        row = MessageRow(
            thread_id=thread_id, seq=thread.next_seq, role=role, agent_id=agent_id, content=content
        )
        session.add(row)
        thread.next_seq += 1
        await session.flush()
        data = message_data(row)
        if live:
            emit(
                session,
                fixture.owner,
                "message.created",
                thread_id=thread_id,
                agent_id=agent_id,
                payload=data,
            )
    return data


async def action(data: dict[str, Any]) -> dict[str, Any]:
    fixture = await Fixture().open()
    try:
        if data["action"] == "init":
            names = data.get("names", ["Alpha", "Beta", "Gamma", "Delta"])
            agents = [await fixture.agent(name) for name in names]
            threads = [await fixture.conversation(agent) for agent in agents]
            group = await fixture.request(
                "POST",
                "/groups/create",
                {
                    "name": data.get("group", "Desk " + uuid4().hex[:6]),
                    "member_ids": [agents[0]["id"], agents[1]["id"]],
                    "participation": "mentions_or_lead",
                    "purpose": data.get("purpose", "Gold research"),
                },
            )
            a, b, c, d = threads[:4]
            await add(fixture, a["id"], "user", None, "Is the market open?", False)
            await add(fixture, a["id"], "assistant", agents[0]["id"], "Yes, it opened.", False)
            await add(fixture, b["id"], "assistant", agents[1]["id"], "First update", False)
            await add(fixture, b["id"], "assistant", agents[1]["id"], "Second update", False)
            await add(fixture, c["id"], "user", None, "Accepted only", False)
            for index in range(int(data.get("bulk", 0))):
                # Enough matching messages for the search to page (32 a page).
                await add(
                    fixture, b["id"], "assistant", agents[1]["id"], f"Paging needle {index}", False
                )
            started = await add(fixture, d["id"], "user", None, "Run started on this", False)
            async with fixture.runtime.db.sessions() as session, session.begin():
                session.add(
                    RunRow(
                        thread_id=d["id"],
                        agent_id=agents[3]["id"],
                        status="completed",
                        input_seq=started["seq"],
                    )
                )
            return {
                "cookies": cookies(fixture),
                "agents": agents,
                "threads": threads,
                "group": group,
            }
        if data["action"] == "message":
            return await add(
                fixture, data["thread"], "assistant", data["agent"], data["content"], True
            )
        if data["action"] == "attention":
            # A fresh transition: an earlier stop (another spec) is lifted first, so the
            # critical item raised here is new.
            controls = await fixture.request("GET", "/trading/controls")
            brokers = fixture.runtime.services(fixture.owner).brokers
            if controls["emergency_stop"]:
                await fixture.request(
                    "PUT",
                    "/trading/controls",
                    {"enabled": controls["enabled"], "emergency_stop": False},
                )
                await attention_tick(fixture.runtime.db, brokers, fixture.owner)
            await fixture.request(
                "PUT", "/trading/controls", {"enabled": False, "emergency_stop": True}
            )
            await attention_tick(fixture.runtime.db, brokers, fixture.owner)
            notifications = (await fixture.client.get("/api/attention")).json()
            return max(
                (row for row in notifications if row["code"] == "emergency_stop"),
                key=lambda row: row["created_at"],
            )
        if data["action"] == "restore":
            # The trading controls exactly as the spec found them.
            return await fixture.request("PUT", "/trading/controls", data["controls"])
        raise ValueError("Unknown chat list fixture action")
    finally:
        await fixture.close(cleanup=False)


if __name__ == "__main__":
    print(json.dumps(asyncio.run(action(json.load(sys.stdin)))))
