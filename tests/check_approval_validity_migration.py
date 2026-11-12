"""Migration 0061 keeps every unresolved operation reconcilable (mandate 14.3.9).

On a disposable PostgreSQL at head: step down below 0061, leave a journal row
``ambiguous`` and a stored pending approval card with its expiry, step up again, then
reconcile. The operation is confirmed from broker evidence without a resend and without
an idempotency conflict: the request, its fingerprint and its operation id are untouched.
The stored card keeps its stored expiry. The downgrade and upgrade run again cleanly.
"""

import asyncio
import json
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from typing import cast
from uuid import uuid4

from check_trading import ScriptedBroker, ScriptedManager, database
from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.schema import OwnerRow, TradeApprovalRow, TradingJournalRow
from lonora_trading.execution import ExecutionService
from lonora_trading.idempotency import trade_fingerprint
from lonora_trading.reconciliation import reconcile_ambiguous
from sqlalchemy import select, text

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
BEFORE = "0060_agent_trading_mode"


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)


async def main() -> None:
    db = database()
    async with db.sessions() as session, session.begin():
        owner = await session.scalar(select(OwnerRow))
        if owner is None:
            owner = OwnerRow(email="validity-migration@example.test", password_hash="x")
            session.add(owner)
            await session.flush()
        owner_id = owner.id
        account = await BrokerSessionRepository().create(
            session,
            owner_id,
            {"provider": "simulation", "account_id": "migration-" + uuid4().hex, "enabled": True},
        )
        account_id = account.id
    request = TradeRequest(
        account_id=account_id,
        operation_id="migration-" + uuid4().hex,
        action="buy",
        symbol="FIXTURE",
        volume=Decimal("0.1"),
    )
    approval_id = str(uuid4())
    expiry = utcnow() + timedelta(minutes=20)
    await db.engine.dispose()

    alembic("downgrade", BEFORE)
    async with db.engine.begin() as connection:
        # Seeded the way the release before 0061 wrote them.
        await connection.execute(
            text(
                "INSERT INTO ln_trading_journal (operation_id, owner_id, account_id,"
                " request_hash, request, status, result, submitted_at, updated_at)"
                " VALUES (:id, :owner, :account, :hash, :request, 'ambiguous', :result,"
                " :at, :at)"
            ),
            {
                "id": request.operation_id,
                "owner": owner_id,
                "account": account_id,
                "hash": trade_fingerprint(request),
                "request": json.dumps(request.model_dump(mode="json")),
                "result": json.dumps(
                    TradeResult(
                        operation_id=request.operation_id,
                        status="ambiguous",
                        code="broker_result_ambiguous",
                        details={"execution": {"send_authorized": True}},
                    ).model_dump(mode="json")
                ),
                "at": utcnow() - timedelta(minutes=5),
            },
        )
        await connection.execute(
            text(
                "INSERT INTO ln_trade_approvals (id, owner_id, agent_id, call_id, requests,"
                " status, results, broker_snapshot, expires_at, created_at, updated_at)"
                " VALUES (:id, :owner, 'stored-agent', 'stored-call', :requests, 'pending',"
                " '[]', '{}', :expiry, :now, :now)"
            ),
            {
                "id": approval_id,
                "owner": owner_id,
                "requests": json.dumps([request.model_dump(mode="json")]),
                "expiry": expiry,
                "now": utcnow(),
            },
        )
    await db.engine.dispose()
    alembic("upgrade", "head")

    async with db.sessions() as session:
        row = await session.get(TradingJournalRow, request.operation_id)
        assert row is not None and row.status == "ambiguous"
        assert row.request == request.model_dump(mode="json")
        assert row.request_hash == trade_fingerprint(request) and row.annotation is None
        card = await session.get(TradeApprovalRow, approval_id)
        assert card is not None and card.expires_at is not None
        assert abs((card.expires_at - expiry).total_seconds()) < 1, "The stored expiry is kept"
        assert card.reason == "" and card.validity == {}

    broker = ScriptedBroker()
    broker.account_id = account_id
    broker.receipts[request.operation_id] = TradeResult(
        operation_id=request.operation_id, status="confirmed", broker_id="migration-deal"
    )
    manager = cast(BrokerManager, ScriptedManager(broker))
    assert await reconcile_ambiguous(db, manager) == 1
    assert broker.sent == 0, "An uncertain operation was resent"
    async with db.sessions() as session:
        row = await session.get(TradingJournalRow, request.operation_id)
        assert row is not None and row.status == "confirmed"
    # The same request again is the same operation: its receipt, no conflict, no send.
    again = await ExecutionService(db, manager).execute(owner_id, request)
    assert again.status == "confirmed" and broker.sent == 0, again
    await db.engine.dispose()

    # Structural round trip.
    alembic("downgrade", BEFORE)
    alembic("upgrade", "head")
    print("PASS an ambiguous operation and a stored card cross 0061 unchanged and reconcile")


if __name__ == "__main__":
    asyncio.run(main())
