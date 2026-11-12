"""Migration 0111 (the judgment label) keeps every unresolved operation reconcilable.

Mandate 14.3.9: "a journal row left ``ambiguous`` before the migration reconciles after
it without a resend or an idempotency conflict." On a disposable PostgreSQL at head:
step down below 0111, leave a journal row ``ambiguous`` with the reason and tolerance the
previous release stored beside it, and a pending card, step up again, then reconcile.
The operation is confirmed from broker evidence without a resend; sending the same
request again with a label is the same operation (its receipt, no conflict, no send).
The stored annotation without a label still validates. The downgrade and upgrade run
again cleanly.
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
from lonora_contracts.trading import TradeAnnotation, TradeRequest, TradeResult
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.schema import OwnerRow, TradeApprovalRow, TradingJournalRow
from lonora_trading.execution import ExecutionService
from lonora_trading.idempotency import trade_fingerprint
from lonora_trading.reconciliation import reconcile_ambiguous
from sqlalchemy import select, text

STORED = {"reason": "Breakout", "tolerance": "1.5"}
ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
BEFORE = "0110_closed_trades"


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)


async def main() -> None:
    db = database()
    async with db.sessions() as session, session.begin():
        owner = await session.scalar(select(OwnerRow))
        if owner is None:
            owner = OwnerRow(email="label-migration@example.test", password_hash="x")
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
        # Seeded the way the release before 0111 wrote them.
        await connection.execute(
            text(
                "INSERT INTO ln_trading_journal (operation_id, owner_id, account_id,"
                " request_hash, request, annotation, status, result, submitted_at,"
                " updated_at)"
                " VALUES (:id, :owner, :account, :hash, :request, :annotation, 'ambiguous',"
                " :result, :at, :at)"
            ),
            {
                "id": request.operation_id,
                "owner": owner_id,
                "account": account_id,
                "hash": trade_fingerprint(request),
                "request": json.dumps(request.model_dump(mode="json")),
                "annotation": json.dumps(STORED),
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
                " status, results, broker_snapshot, expires_at, reason, validity,"
                " created_at, updated_at)"
                " VALUES (:id, :owner, 'stored-agent', 'stored-call', :requests, 'pending',"
                " '[]', '{}', :expiry, 'Breakout', :validity, :now, :now)"
            ),
            {
                "id": approval_id,
                "owner": owner_id,
                "requests": json.dumps([request.model_dump(mode="json")]),
                "expiry": expiry,
                "validity": json.dumps({"tolerance": "1.5"}),
                "now": utcnow(),
            },
        )
    await db.engine.dispose()
    alembic("upgrade", "head")

    async with db.sessions() as session:
        row = await session.get(TradingJournalRow, request.operation_id)
        assert row is not None and row.status == "ambiguous"
        assert row.request == request.model_dump(mode="json")
        assert row.request_hash == trade_fingerprint(request) and row.annotation == STORED
        # A stored annotation without a label still validates: the field is optional.
        assert TradeAnnotation.model_validate(row.annotation).label == ""
        card = await session.get(TradeApprovalRow, approval_id)
        assert card is not None and card.expires_at is not None
        assert abs((card.expires_at - expiry).total_seconds()) < 1, "The stored expiry is kept"
        assert card.reason == "Breakout" and card.label is None

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
    # The same request again, now with a label, is the same operation: its receipt, no
    # conflict, no send, and the stored annotation is not rewritten.
    labelled = TradeAnnotation(reason="Breakout", tolerance=Decimal("1.5"), label="scale_in")
    again = await ExecutionService(db, manager).execute(owner_id, request, annotation=labelled)
    assert again.status == "confirmed" and broker.sent == 0, again
    async with db.sessions() as session:
        row = await session.get(TradingJournalRow, request.operation_id)
        assert row is not None and row.annotation == STORED
    await db.engine.dispose()

    # Structural round trip.
    alembic("downgrade", BEFORE)
    alembic("upgrade", "head")
    print("PASS an ambiguous operation and a stored card cross 0111 unchanged and reconcile")


if __name__ == "__main__":
    asyncio.run(main())
