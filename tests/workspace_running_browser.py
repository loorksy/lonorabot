"""Real PostgreSQL fixture for "What is running" (tests/web/what-is-running.spec.mjs and
tests/mobile/what-is-running.spec.mjs): two agents with processes in the listing the
Gateway keeps, and a read of the stop requests the owner's taps made."""

import asyncio
import json
import sys
from datetime import UTC, datetime, timedelta
from typing import Any

from check_streaming import Fixture
from lonora_db.schema import WorkspaceRunningRow, WorkspaceStopRow
from lonora_db.workspace_running import record_listing
from sqlalchemy import delete, select, update


def cookies(fixture: Fixture) -> list[dict[str, str | None]]:
    return [{"name": cookie.name, "value": cookie.value} for cookie in fixture.client.cookies.jar]


def process(pid: int, agent: str, command: str) -> dict[str, Any]:
    return {
        "pid": pid,
        "ppid": 1,
        "agent_id": agent,
        "command": command,
        "started_at": datetime.now(UTC).timestamp() - 600,
    }


async def action(data: dict[str, Any]) -> dict[str, Any]:
    fixture = await Fixture().open()
    try:
        if data["action"] == "init":
            trader = await fixture.agent("Gold desk")
            research = await fixture.agent("Research")
            async with fixture.runtime.db.sessions() as session, session.begin():
                await session.execute(delete(WorkspaceStopRow))
                await record_listing(
                    session,
                    fixture.owner,
                    [
                        process(4101, trader["id"], "python3 listener.py --symbol XAUUSD"),
                        process(4102, trader["id"], "node price-feed.js"),
                        process(4201, research["id"], "python3 scrape.py"),
                    ],
                    datetime.now(UTC),
                )
            return {"cookies": cookies(fixture), "trader": trader, "research": research}
        if data["action"] == "stops":
            async with fixture.runtime.db.sessions() as session:
                rows = (await session.scalars(select(WorkspaceStopRow))).all()
            return {"stops": [{"pid": row.pid, "agent_id": row.agent_id} for row in rows]}
        if data["action"] == "empty":
            async with fixture.runtime.db.sessions() as session, session.begin():
                await record_listing(session, fixture.owner, [], datetime.now(UTC))
            return {"empty": True}
        if data["action"] == "unknown":
            # No listing yet: the workspace has not answered since the Gateway started.
            async with fixture.runtime.db.sessions() as session, session.begin():
                await session.execute(delete(WorkspaceRunningRow))
            return {"unknown": True}
        if data["action"] == "carried_out":
            # What the Gateway does: the stops are taken, and a new process has started.
            async with fixture.runtime.db.sessions() as session, session.begin():
                await session.execute(update(WorkspaceStopRow).values(done_at=datetime.now(UTC)))
                await record_listing(
                    session,
                    fixture.owner,
                    [process(4301, data["trader"]["id"], "python3 restarted.py")],
                    datetime.now(UTC),
                )
            return {"carried_out": True}
        if data["action"] == "stale":
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(WorkspaceRunningRow, fixture.owner)
                assert row is not None
                row.listed_at = datetime.now(UTC) - timedelta(minutes=5)
                row.processes = [
                    {
                        "pid": 4401,
                        "agent_id": data["trader"]["id"],
                        "command": "python3 old.py",
                        "started_at": None,
                    }
                ]
            return {"stale": True}
        if data["action"] == "cleanup":
            async with fixture.runtime.db.sessions() as session, session.begin():
                await session.execute(delete(WorkspaceStopRow))
                await session.execute(delete(WorkspaceRunningRow))
            for agent in (data["trader"]["id"], data["research"]["id"]):
                await fixture.client.delete(f"/api/agents/{agent}")
            return {"cleaned": True}
    finally:
        await fixture.close(cleanup=False)
    raise ValueError("Unknown What is running fixture action")


if __name__ == "__main__":
    print(json.dumps(asyncio.run(action(json.load(sys.stdin)))))
