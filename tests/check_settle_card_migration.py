"""Migration 0101: stored resolve_operation cards become Settle Uncertain Operation cards.

On a disposable PostgreSQL at head: step down below 0101, store a pending
``resolve_operation`` card as the previous release wrote it (its payload hash covers the
old kind), step up. The card is a ``settle_operation`` card with the hash of its new kind,
so the server finds it as the live card for that operation; payload, status and expiry
are unchanged. The owner's answer on it then settles the operation as the owner's word:
``resolved``, never ``confirmed``, and no Execution Receipt. Downgrade and upgrade again.
"""

import asyncio
import json
import subprocess
import sys
from datetime import timedelta
from decimal import Decimal
from uuid import uuid4

from check_trading import database
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import OperationResolution, TradeRequest
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.owner_actions import payload_hash, pending_effect
from lonora_db.schema import (
    AgentRow,
    ExecutionReceiptRow,
    OwnerActionRow,
    OwnerRow,
    TradingJournalRow,
)
from lonora_trading.idempotency import trade_fingerprint
from lonora_trading.owner_controls import attest_operation
from sqlalchemy import select, text

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
BEFORE = "0100_execution_receipts"


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)


async def main() -> None:
    db = database()
    async with db.sessions() as session, session.begin():
        owner = await session.scalar(select(OwnerRow))
        if owner is None:
            owner = OwnerRow(email="settle-migration@example.test", password_hash="x")
            session.add(owner)
            await session.flush()
        owner_id = owner.id
        account = await BrokerSessionRepository().create(
            session,
            owner_id,
            {"provider": "simulation", "account_id": "settle-" + uuid4().hex, "enabled": True},
        )
        agent = AgentRow(owner_id=owner_id, name="Gold")
        session.add(agent)
        await session.flush()
        account_id, agent_id = account.id, agent.id
    request = TradeRequest(
        account_id=account_id,
        operation_id="settle-" + uuid4().hex,
        action="buy",
        symbol="FIXTURE",
        volume=Decimal("0.1"),
    )
    card_id = str(uuid4())
    payload = {"operation_id": request.operation_id}
    expiry = utcnow() + timedelta(days=7)
    await db.engine.dispose()

    alembic("downgrade", BEFORE)
    async with db.engine.begin() as connection:
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
                    {
                        "operation_id": request.operation_id,
                        "status": "ambiguous",
                        "code": "broker_result_ambiguous",
                        "details": {"execution": {"agent_id": agent_id, "send_authorized": True}},
                    }
                ),
                "at": utcnow(),
            },
        )
        await connection.execute(
            text(
                "INSERT INTO ln_owner_actions (id, owner_id, agent_id, source, kind, subject,"
                " payload, payload_hash, status, result, expires_at, created_at, updated_at)"
                " VALUES (:id, :owner, :agent, 'system', 'resolve_operation', :subject,"
                " :payload, :hash, 'pending', '{}', :expires, :at, :at)"
            ),
            {
                "id": card_id,
                "owner": owner_id,
                "agent": agent_id,
                "subject": "operation:" + request.operation_id,
                "payload": json.dumps(payload),
                "hash": payload_hash("resolve_operation", payload),
                "expires": expiry,
                "at": utcnow(),
            },
        )
    alembic("upgrade", "head")

    async with db.sessions() as session:
        card = await session.get(OwnerActionRow, card_id)
        assert card is not None and card.kind == "settle_operation"
        assert card.payload == payload and card.status == "pending"
        assert card.payload_hash == payload_hash("settle_operation", payload)
        assert card.expires_at == expiry
        found = await pending_effect(
            session, agent_id, "settle_operation", payload_hash("settle_operation", payload)
        )
        assert found is not None and found.id == card_id
    print("PASS a stored resolve_operation card is the live Settle card for its operation")

    async with db.sessions() as session, session.begin():
        await attest_operation(
            session,
            owner_id,
            request.operation_id,
            OperationResolution(outcome="executed"),
            {"kind": "owner", "owner_id": owner_id},
        )
    async with db.sessions() as session:
        row = await session.get(TradingJournalRow, request.operation_id)
        assert row is not None and row.status == "resolved"
        assert row.result["details"]["resolution"]["broker_confirmed"] is False
        assert await session.get(ExecutionReceiptRow, request.operation_id) is None
    print("PASS the owner's Executed answer is recorded in the journal, never as a receipt")

    await db.engine.dispose()
    alembic("downgrade", BEFORE)
    async with db.engine.begin() as connection:
        kind = (
            await connection.execute(
                text("SELECT kind FROM ln_owner_actions WHERE id = :id"), {"id": card_id}
            )
        ).scalar_one()
        assert kind == "resolve_operation"
    alembic("upgrade", "head")
    print("PASS 0101 downgrades and upgrades again cleanly")
    await db.close()


if __name__ == "__main__":
    asyncio.run(main())
