"""Migration 0100: Execution Receipts replace ln_financial_receipts (mandate 10.3, 3.1.2).

On a disposable PostgreSQL at head: step down below 0100 and seed, as the previous
release wrote them, a confirmed operation anchored in a conversation (shown there as an
order line), a confirmed owner's order without an anchor, a failed one and an ambiguous
one. Step up: only the anchored confirmed operation gets a receipt, at its anchor and
with its agent. The ambiguous operation then reconciles from broker evidence, without a
resend, and posts its one receipt. A stored ln_financial_receipts row makes the upgrade
refuse rather than drop it. The downgrade and upgrade run again cleanly.
"""

import asyncio
import json
import subprocess
import sys
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from check_trading import ScriptedBroker, ScriptedManager, database
from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.schema import AgentRow, ExecutionReceiptRow, OwnerRow, ThreadRow
from lonora_trading.idempotency import trade_fingerprint
from lonora_trading.reconciliation import reconcile_ambiguous
from sqlalchemy import select, text

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
BEFORE = "0061_trade_approval_validity"


def alembic(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*ALEMBIC, *arguments], capture_output=True, text=True)


async def main() -> None:
    db = database()
    async with db.sessions() as session, session.begin():
        owner = await session.scalar(select(OwnerRow))
        if owner is None:
            owner = OwnerRow(email="receipt-migration@example.test", password_hash="x")
            session.add(owner)
            await session.flush()
        owner_id = owner.id
        account = await BrokerSessionRepository().create(
            session,
            owner_id,
            {"provider": "simulation", "account_id": "migration-" + uuid4().hex, "enabled": True},
        )
        account_id = account.id
        agent = AgentRow(owner_id=owner_id, name="Gold")
        session.add(agent)
        await session.flush()
        thread = ThreadRow(owner_id=owner_id, agent_id=agent.id)
        session.add(thread)
        await session.flush()
        agent_id, thread_id = agent.id, thread.id

    def request() -> TradeRequest:
        return TradeRequest(
            account_id=account_id,
            operation_id="migration-" + uuid4().hex,
            action="buy",
            symbol="FIXTURE",
            volume=Decimal("0.1"),
        )

    anchored, owners, failed, ambiguous = request(), request(), request(), request()
    await db.engine.dispose()

    assert alembic("downgrade", BEFORE).returncode == 0
    async with db.engine.begin() as connection:

        async def seed(
            item: TradeRequest, status: str, *, anchor: bool, agent: str | None = None
        ) -> None:
            result: dict[str, Any] = {
                "operation_id": item.operation_id,
                "status": status,
                "broker_id": "ticket-1" if status == "confirmed" else None,
                "details": {
                    "execution": {"agent_id": agent, "run_id": None, "send_authorized": True}
                },
            }
            await connection.execute(
                text(
                    "INSERT INTO ln_trading_journal (operation_id, owner_id, account_id,"
                    " request_hash, request, status, result, submitted_at, updated_at,"
                    " thread_id, timeline_seq)"
                    " VALUES (:id, :owner, :account, :hash, :request, :status, :result,"
                    " :at, :at, :thread, :seq)"
                ),
                {
                    "id": item.operation_id,
                    "owner": owner_id,
                    "account": account_id,
                    "hash": trade_fingerprint(item),
                    "request": json.dumps(item.model_dump(mode="json")),
                    "status": status,
                    "result": json.dumps(result),
                    "at": utcnow(),
                    "thread": thread_id if anchor else None,
                    "seq": 7 if anchor else None,
                },
            )

        await seed(anchored, "confirmed", anchor=True, agent=agent_id)
        await seed(owners, "confirmed", anchor=False)
        await seed(failed, "failed", anchor=True, agent=agent_id)
        await seed(ambiguous, "ambiguous", anchor=True, agent=agent_id)
        # A stored row in the dropped table: the upgrade refuses instead of deleting it.
        await connection.execute(
            text(
                "INSERT INTO ln_financial_receipts (state, id, owner_id, payload, version,"
                " created_at, updated_at) VALUES ('{}', :id, :owner, '{}', 1, :at, :at)"
            ),
            {"id": str(uuid4()), "owner": owner_id, "at": utcnow()},
        )
    refused = alembic("upgrade", "head")
    assert refused.returncode != 0 and "refusing to drop receipts" in refused.stderr
    async with db.engine.begin() as connection:
        await connection.execute(text("DELETE FROM ln_financial_receipts"))
    upgraded = alembic("upgrade", "head")
    assert upgraded.returncode == 0, upgraded.stderr
    print("PASS a stored ln_financial_receipts row stops the upgrade; an empty table is dropped")

    async with db.sessions() as session:
        rows = list(
            await session.scalars(
                select(ExecutionReceiptRow).where(ExecutionReceiptRow.owner_id == owner_id)
            )
        )
    assert [row.operation_id for row in rows] == [anchored.operation_id], rows
    assert rows[0].thread_id == thread_id and rows[0].timeline_seq == 7
    assert rows[0].agent_id == agent_id
    print("PASS an anchored confirmed operation keeps its place as a receipt; nothing else")

    broker = ScriptedBroker()
    broker.receipts[ambiguous.operation_id] = TradeResult(
        operation_id=ambiguous.operation_id, status="confirmed", broker_id="ticket-2"
    )
    manager = cast(BrokerManager, ScriptedManager(broker))
    assert await reconcile_ambiguous(db, manager) == 1 and broker.sent == 0
    async with db.sessions() as session:
        posted = await session.get(ExecutionReceiptRow, ambiguous.operation_id)
    assert posted is not None and posted.thread_id == thread_id
    print("PASS an operation left ambiguous before 0100 reconciles after it into one receipt")

    await db.engine.dispose()
    assert alembic("downgrade", BEFORE).returncode == 0
    assert alembic("upgrade", "head").returncode == 0
    print("PASS 0100 downgrades and upgrades again cleanly")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
