"""Durable financial records, guarded deletes and gateway readiness on real PostgreSQL.

Needs an explicit disposable, freshly migrated *_test database. Checks:
- migration 0036 removes the cascades, refuses a lossy downgrade while a record has
  outlived its parent, and round-trips once it has not;
- DELETE of an agent, a conversation or a broker connection is refused (409, owner text
  code) while a trade it touches is uncertain, and otherwise keeps every financial record;
- /ready is 503 until a gateway heartbeat is fresh and no critical step has stalled.
"""

import asyncio
import subprocess
import sys
from typing import Any

from check_streaming import Fixture
from lonora_contracts.domain import utcnow
from lonora_db.schema import (
    BrokerSessionRow,
    GatewayRow,
    RunRow,
    ThreadRow,
    TradeApprovalRow,
    TradingJournalRow,
)
from sqlalchemy import select, text

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
LINKS = {
    ("ln_account_authorities", "agent_id"),
    ("ln_account_authorities", "account_id"),
    ("ln_account_authorities", "thread_id"),
    ("ln_super_bot_requests", "agent_id"),
    ("ln_super_bot_requests", "goal_id"),
    ("ln_super_bot_requests", "thread_id"),
    ("ln_trade_approvals", "agent_id"),
    ("ln_trade_approvals", "run_id"),
    ("ln_trade_approvals", "thread_id"),
    ("ln_goal_decisions", "goal_id"),
    ("ln_trading_goals", "agent_id"),
    ("ln_trading_goals", "thread_id"),
    ("ln_trading_restrictions", "account_id"),
    ("ln_trading_restrictions", "agent_id"),
}


async def delete_actions(f: Fixture) -> dict[tuple[str, str], str]:
    async with f.runtime.db.sessions() as session:
        rows = await session.execute(
            text(
                "SELECT conrelid::regclass::text, a.attname, c.confdeltype::text "
                "FROM pg_constraint c JOIN pg_attribute a "
                "ON a.attrelid = c.conrelid AND a.attnum = ANY(c.conkey) WHERE c.contype = 'f'"
            )
        )
        return {
            (table, column): action for table, column, action in rows if (table, column) in LINKS
        }


async def alembic(f: Fixture, *arguments: str) -> int:
    await f.runtime.db.close()
    result = await asyncio.to_thread(
        subprocess.run, [*ALEMBIC, *arguments], stdout=subprocess.DEVNULL, stderr=subprocess.PIPE
    )
    return result.returncode


async def migration(f: Fixture) -> None:
    head = await delete_actions(f)
    contexts = {("ln_account_authorities", "thread_id"), ("ln_super_bot_requests", "thread_id")}
    contexts |= {("ln_trade_approvals", "run_id"), ("ln_trade_approvals", "thread_id")}
    contexts |= {("ln_trading_goals", "thread_id")}
    assert head == dict.fromkeys(contexts, "n"), head
    agent = await f.agent("Durable")
    async with f.runtime.db.sessions() as session, session.begin():
        session.add(
            TradeApprovalRow(
                id="orphan-approval",
                owner_id=f.owner,
                run_id=None,
                thread_id=None,
                agent_id=agent["id"],
                call_id="call",
                requests=[],
                status="completed",
            )
        )
    # A record that outlived its parent cannot be squeezed back under a cascade.
    assert await alembic(f, "downgrade", "0035_agent_tool_usage") != 0
    assert await delete_actions(f) == head
    async with f.runtime.db.sessions() as session, session.begin():
        orphan = await session.get(TradeApprovalRow, "orphan-approval")
        assert orphan
        await session.delete(orphan)
    assert await alembic(f, "downgrade", "0035_agent_tool_usage") == 0
    assert set((await delete_actions(f)).values()) == {"c"} and len(await delete_actions(f)) == 14
    assert await alembic(f, "upgrade", "head") == 0
    assert await delete_actions(f) == head
    print("PASS: migration 0036 removes cascades, refuses a lossy downgrade and round-trips")


async def journal(f: Fixture, operation: str, account: str, agent: str, status: str) -> None:
    async with f.runtime.db.sessions() as session, session.begin():
        row = await session.get(TradingJournalRow, operation)
        if row is None:
            row = TradingJournalRow(
                operation_id=operation,
                owner_id=f.owner,
                account_id=account,
                request_hash="h",
                request={"symbol": "XAUUSD"},
                result={"details": {"execution": {"agent_id": agent}}},
                submitted_at=utcnow(),
            )
            session.add(row)
        row.status = status


async def delete(f: Fixture, path: str) -> tuple[int, dict[str, Any]]:
    response = await f.client.delete("/api" + path)
    return response.status_code, response.json()


async def deletes(f: Fixture) -> None:
    agent = await f.agent("Gold desk")
    thread = await f.conversation(agent)
    async with f.runtime.db.sessions() as session, session.begin():
        account = BrokerSessionRow(owner_id=f.owner, payload={"provider": "simulation"})
        run = RunRow(thread_id=thread["id"], agent_id=agent["id"], status="completed")
        session.add_all([account, run])
        await session.flush()
        account_id, run_id = account.id, run.id
        session.add(
            TradeApprovalRow(
                id="pending-" + run_id[:8],
                owner_id=f.owner,
                run_id=run_id,
                thread_id=thread["id"],
                agent_id=agent["id"],
                call_id="call",
                requests=[{"account_id": account_id, "symbol": "XAUUSD"}],
                status="pending",
            )
        )
    await journal(f, "op-durable-agent", account_id, agent["id"], "ambiguous")
    status, body = await delete(f, "/agents/" + agent["id"])
    assert (status, body["code"]) == (409, "delete_blocked_unresolved_operation"), body
    status, body = await delete(f, "/trading/connections/" + account_id)
    assert (status, body["code"]) == (409, "delete_blocked_unresolved_operation"), body
    await journal(f, "op-durable-agent", account_id, agent["id"], "confirmed")
    assert (await delete(f, "/threads/" + thread["id"]))[0] == 200
    async with f.runtime.db.sessions() as session:
        approval = await session.get(TradeApprovalRow, "pending-" + run_id[:8])
        assert await session.get(ThreadRow, thread["id"]) is None
    # The owner's pending request was narrowed away, never deleted with the conversation.
    assert approval and approval.status == "cancelled" and approval.thread_id is None
    assert approval.run_id is None and approval.agent_id == agent["id"]
    assert (await delete(f, "/agents/" + agent["id"]))[0] == 200
    assert (await delete(f, "/trading/connections/" + account_id))[0] == 200
    async with f.runtime.db.sessions() as session:
        kept = await session.get(TradingJournalRow, "op-durable-agent")
        approval = await session.get(TradeApprovalRow, "pending-" + run_id[:8])
    assert kept and kept.status == "confirmed" and approval
    print("PASS: deletes refuse an uncertain trade (409) and keep approvals and the journal")


async def readiness(f: Fixture) -> None:
    async with f.runtime.db.sessions() as session, session.begin():
        for row in await session.scalars(select(GatewayRow)):
            await session.delete(row)
    response = await f.client.get("/ready")
    assert response.status_code == 503 and response.json()["gateway"]["ready"] is False
    async with f.runtime.db.sessions() as session, session.begin():
        session.add(
            GatewayRow(
                id="check-gateway",
                state="running",
                liveness={"steps": {"reconcile": {"critical": True, "stalled": True}}},
            )
        )
    response = await f.client.get("/ready")
    assert response.status_code == 503
    assert response.json()["gateway"]["stalled"] == {"check-gateway": ["reconcile"]}
    async with f.runtime.db.sessions() as session, session.begin():
        row = await session.get(GatewayRow, "check-gateway")
        assert row
        row.liveness = {"steps": {"reconcile": {"critical": True, "stalled": False}}}
        row.heartbeat_at = utcnow()
    response = await f.client.get("/ready")
    assert response.status_code == 200 and response.json()["gateway"]["ready"] is True
    async with f.runtime.db.sessions() as session, session.begin():
        row = await session.get(GatewayRow, "check-gateway")
        assert row
        await session.delete(row)
    print("PASS: /ready is 503 until a fresh heartbeat reports no stalled critical step")


async def main() -> None:
    f = await Fixture().open()
    try:
        await migration(f)
        await deletes(f)
        await readiness(f)
    finally:
        await f.client.aclose()
        await f.runtime.db.close()


if __name__ == "__main__":
    asyncio.run(main())
