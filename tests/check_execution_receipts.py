"""The Execution Receipt on PostgreSQL (mandate 10.3, 11.2, 3.1.2, 6.3, 6.4).

Every path that confirms an operation posts exactly one receipt, in the conversation it
belongs to: a tool in Full, an approved card in Ask, reconciliation of an uncertain send,
recovery after a worker died after the broker effect, and the owner's own order. An
unconfirmed, rejected, blocked or owner-settled operation posts none; a replay posts no
second one; deleting the conversation or the agent keeps it. Scripted broker only; run on
a fresh disposable *_test database.
"""

import asyncio
import sys
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

from check_trading import CrashAfterSendBroker, ScriptedBroker, ScriptedManager, database
from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.agent_permissions import PermissionChange
from lonora_contracts.domain import utcnow
from lonora_contracts.runs import Lease
from lonora_contracts.trading import (
    OperationResolution,
    TradeAnnotation,
    TradeRequest,
    TradeResult,
)
from lonora_core.user_error import LonoraError
from lonora_db import execution_receipts as receipts_module
from lonora_db.agent_permissions import change_permission
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.execution_receipts import thread_receipts
from lonora_db.schema import (
    AgentRow,
    EventRow,
    ExecutionReceiptRow,
    OwnerRow,
    RunRow,
    ThreadRow,
    TradeApprovalRow,
    TradingJournalRow,
)
from lonora_db.trading_journal import resolve_operation
from lonora_trading.execution import ExecutionService
from lonora_trading.owner_controls import attest_operation
from lonora_trading.reconciliation import reconcile_ambiguous
from sqlalchemy import delete, func, select

SYMBOL = "FIXTURE"


class FillingBroker(ScriptedBroker):
    """Reports a fill the way MetaApi does: the position ticket, volume and price."""

    def __init__(self) -> None:
        super().__init__()
        self.reject = False

    async def execute(self, request: TradeRequest, before_send: Any = None) -> TradeResult:
        if self.reject:
            assert before_send is not None
            await before_send()
            self.sent += 1
            return TradeResult(
                operation_id=request.operation_id, status="failed", code="market_closed"
            )
        result = await super().execute(request, before_send)
        filled = result.model_copy(
            update={
                "broker_id": "ticket-" + request.operation_id[-6:],
                "details": {
                    **result.details,
                    "position_id": "ticket-" + request.operation_id[-6:],
                    "volume": str(request.volume) if request.volume else None,
                    "price": "100.01",
                },
            }
        )
        self.receipts[request.operation_id] = filled
        return filled


async def count(db: Any, operation_id: str) -> int:
    async with db.sessions() as session:
        return int(
            await session.scalar(
                select(func.count())
                .select_from(ExecutionReceiptRow)
                .where(ExecutionReceiptRow.operation_id == operation_id)
            )
            or 0
        )


async def receipt(db: Any, operation_id: str) -> ExecutionReceiptRow:
    async with db.sessions() as session:
        row = await session.get(ExecutionReceiptRow, operation_id)
        assert row is not None, operation_id
        return row


async def checks() -> None:
    db = database()
    broker = FillingBroker()
    manager = cast(BrokerManager, ScriptedManager(broker))
    service = ExecutionService(db, manager)
    async with db.sessions() as session, session.begin():
        owner = OwnerRow(email=f"receipts-{uuid4().hex[:8]}@example.test", password_hash="x")
        session.add(owner)
        await session.flush()
        owner_id = owner.id
        account = await BrokerSessionRepository().create(
            session,
            owner_id,
            {"provider": "simulation", "account_id": "receipts-" + uuid4().hex, "enabled": True},
        )
        account_id = account.id
        lonora = AgentRow(owner_id=owner_id, name="Lonora", role="personal")
        gold = AgentRow(owner_id=owner_id, name="Gold", trading_mode="full")
        euro = AgentRow(owner_id=owner_id, name="Euro", trading_mode="ask")
        session.add_all([lonora, gold, euro])
        await session.flush()
        lonora_id, gold_id, euro_id = lonora.id, gold.id, euro.id
        lonora_thread = ThreadRow(owner_id=owner_id, agent_id=lonora_id)
        gold_thread = ThreadRow(owner_id=owner_id, agent_id=gold_id)
        euro_thread = ThreadRow(owner_id=owner_id, agent_id=euro_id)
        session.add_all([lonora_thread, gold_thread, euro_thread])
        await session.flush()
        threads = {"lonora": lonora_thread.id, "gold": gold_thread.id, "euro": euro_thread.id}

        def leased(agent: str, thread: str) -> RunRow:
            return RunRow(
                thread_id=thread,
                agent_id=agent,
                status="running",
                lease_owner="receipt-worker",
                lease_fence=1,
                lease_expires_at=utcnow() + timedelta(minutes=30),
            )

        gold_run, euro_run = leased(gold_id, threads["gold"]), leased(euro_id, threads["euro"])
        session.add_all([gold_run, euro_run])
        await session.flush()
        gold_lease = Lease(run_id=gold_run.id, owner="receipt-worker", fence=1)
        euro_lease = Lease(run_id=euro_run.id, owner="receipt-worker", fence=1)
        # The old ladder still answers first until W-AUTH removes it; the mode decides.
        for agent in (gold_id, euro_id):
            await change_permission(
                session, owner_id, agent, PermissionChange(level="supervised", expected_revision=0)
            )

    def buy(volume: str = "0.1") -> TradeRequest:
        return TradeRequest(
            account_id=account_id,
            operation_id="receipt-" + uuid4().hex,
            action="buy",
            symbol=SYMBOL,
            volume=volume,  # type: ignore[arg-type]
            stop_loss="95",  # type: ignore[arg-type]
        )

    reason = TradeAnnotation(reason="Breakout above 100 on the London open")

    # 1. A tool in Full: one receipt in the run's conversation, with the agent's reason.
    full = buy()
    result = await service.execute(owner_id, full, gold_lease, annotation=reason)
    assert result.status == "confirmed", result
    posted = await receipt(db, full.operation_id)
    assert posted.thread_id == threads["gold"] and posted.agent_id == gold_id
    async with db.sessions() as session:
        shown = await thread_receipts(session, owner_id, threads["gold"])
    assert [item["operation_id"] for item in shown] == [full.operation_id]
    card = shown[0]
    assert card["kind"] == "fill" and card["action"] == "buy" and card["volume"] == "0.1"
    assert card["price"] == "100.01" and card["ticket"] == "ticket-" + full.operation_id[-6:]
    assert card["reason"] == reason.reason
    # Broker-confirmed, the account state not yet read back: never shown as verified.
    assert card["verification"] in {"pending", "unverified"}, card["verification"]
    # A replay is answered from the journal and posts nothing new.
    again = await service.execute(owner_id, full, gold_lease, annotation=reason)
    assert again.status == "confirmed" and await count(db, full.operation_id) == 1
    async with db.sessions() as session:
        events = await session.scalar(
            select(func.count())
            .select_from(EventRow)
            .where(
                EventRow.kind == "trading.receipt_posted",
                EventRow.payload["operation_id"].as_string() == full.operation_id,
            )
        )
    assert events == 1
    print("PASS a tool order in Full posts one receipt in its conversation; a replay none")

    # 2. An approved card in Ask: the same door posts one receipt in the card's conversation.
    asked = buy("0.2")
    async with db.sessions() as session, session.begin():
        session.add(
            TradeApprovalRow(
                id=str(uuid4()),
                owner_id=owner_id,
                run_id=euro_lease.run_id,
                thread_id=threads["euro"],
                agent_id=euro_id,
                call_id="call-" + uuid4().hex[:8],
                requests=[asked.model_dump(mode="json")],
                status="approved",
                reason=reason.reason,
            )
        )
    result = await service.execute(owner_id, asked, euro_lease, annotation=reason)
    assert result.status == "confirmed", result
    posted = await receipt(db, asked.operation_id)
    assert posted.thread_id == threads["euro"] and posted.agent_id == euro_id
    print("PASS an approved Trade Approval posts one receipt in the requesting conversation")

    # 3. The owner's own order (no run): Lonora's conversation, with no reason.
    owned = buy("0.3")
    result = await service.execute(owner_id, owned, annotation=reason)
    assert result.status == "confirmed", result
    posted = await receipt(db, owned.operation_id)
    assert posted.thread_id == threads["lonora"] and posted.agent_id is None
    async with db.sessions() as session:
        shown = await thread_receipts(session, owner_id, threads["lonora"])
    assert [item["reason"] for item in shown] == [None]
    print("PASS the owner's own order posts one receipt in Lonora's conversation, no reason")

    # 4. Rejected and blocked operations post none.
    broker.reject = True
    rejected = buy()
    assert (await service.execute(owner_id, rejected, gold_lease)).status == "failed"
    broker.reject = False
    assert await count(db, rejected.operation_id) == 0
    blocked = buy()
    try:
        await service.execute(owner_id, blocked, euro_lease)
    except LonoraError as error:
        assert error.code == "trade_approval_required", error.code
    else:
        raise AssertionError("an unapproved request in Ask must not be sent")
    assert await count(db, blocked.operation_id) == 0
    print("PASS a rejected or refused operation posts no receipt")

    # 5. An uncertain send: none while ambiguous; one when reconciliation confirms it.
    broker.mode = "timeout"
    uncertain = buy()
    assert (await service.execute(owner_id, uncertain, gold_lease)).status == "ambiguous"
    broker.mode = "confirmed"
    assert await count(db, uncertain.operation_id) == 0
    assert await reconcile_ambiguous(db, manager) == 1
    assert await count(db, uncertain.operation_id) == 1
    assert (await receipt(db, uncertain.operation_id)).thread_id == threads["gold"]
    sent = broker.sent
    assert await reconcile_ambiguous(db, manager) == 0
    assert (await service.execute(owner_id, uncertain, gold_lease)).status == "confirmed"
    assert await count(db, uncertain.operation_id) == 1 and broker.sent == sent
    print("PASS reconciliation of an uncertain send posts exactly one receipt, never resends")

    # 6. The owner settles an uncertain operation: the owner's word, never a receipt.
    broker.mode = "timeout"
    settled = buy()
    assert (await service.execute(owner_id, settled, gold_lease)).status == "ambiguous"
    broker.mode = "confirmed"
    broker.receipts.pop(settled.operation_id)
    async with db.sessions() as session, session.begin():
        await resolve_operation(
            session,
            owner_id,
            settled.operation_id,
            OperationResolution(outcome="executed"),
            {"kind": "owner", "owner_id": owner_id},
        )
    assert await count(db, settled.operation_id) == 0
    print("PASS the owner's Executed answer settles the operation without a receipt")

    # 6b. "Unknown" is the owner's word that the outcome is still unknown: it is recorded,
    # the operation stays uncertain, and reconciliation goes on (6.3). When the broker's
    # evidence arrives, the operation is confirmed with its one receipt and no resend.
    broker.mode = "timeout"
    unknown = buy()
    assert (await service.execute(owner_id, unknown, gold_lease)).status == "ambiguous"
    broker.mode = "confirmed"
    evidence = broker.receipts.pop(unknown.operation_id)
    async with db.sessions() as session, session.begin():
        await attest_operation(
            session,
            owner_id,
            unknown.operation_id,
            OperationResolution(outcome="unknown"),
            {"kind": "owner", "owner_id": owner_id},
        )
    async with db.sessions() as session:
        row = await session.get(TradingJournalRow, unknown.operation_id)
        assert row is not None and row.status == "ambiguous", row and row.status
        answers = row.result["details"]["owner_answers"]
        assert [item["outcome"] for item in answers] == ["unknown"]
        assert answers[0]["broker_confirmed"] is False
    assert await count(db, unknown.operation_id) == 0
    sent = broker.sent
    broker.receipts[unknown.operation_id] = evidence
    assert await reconcile_ambiguous(db, manager) == 1
    async with db.sessions() as session:
        row = await session.get(TradingJournalRow, unknown.operation_id)
        assert row is not None and row.status == "confirmed"
    assert await count(db, unknown.operation_id) == 1 and broker.sent == sent
    print("PASS an Unknown answer keeps reconciling; later broker evidence posts one receipt")

    # 7. A worker killed after the broker effect, before the journal: recovery posts one.
    killed = buy()
    with TemporaryDirectory(prefix="lonora-receipt-crash-") as temporary:
        receipt_file = Path(temporary) / "receipt.json"
        child = await asyncio.create_subprocess_exec(
            sys.executable,
            __file__,
            "crash-after-send",
            owner_id,
            killed.model_dump_json(),
            str(receipt_file),
        )
        assert await asyncio.wait_for(child.wait(), 30) == 23
        observed = TradeResult.model_validate_json(receipt_file.read_text())
    async with db.sessions() as session, session.begin():
        row = await session.get(TradingJournalRow, killed.operation_id, with_for_update=True)
        assert row is not None and row.status == "submitted"
        row.submitted_at = utcnow() - timedelta(minutes=2)
    assert await count(db, killed.operation_id) == 0
    restarted = ScriptedBroker()
    restarted.receipts[killed.operation_id] = observed
    restarted_manager = cast(BrokerManager, ScriptedManager(restarted))
    assert await reconcile_ambiguous(db, restarted_manager) == 1
    assert await count(db, killed.operation_id) == 1 and restarted.sent == 0
    # The owner's own order had no run: its receipt goes to Lonora's conversation.
    assert (await receipt(db, killed.operation_id)).thread_id == threads["lonora"]
    assert await reconcile_ambiguous(db, restarted_manager) == 0
    assert await count(db, killed.operation_id) == 1
    print("PASS a restart between the broker effect and the journal posts exactly one receipt")

    # 8. A failure while placing the receipt never undoes the broker's confirmation.
    async def broken(*_: Any) -> None:
        raise RuntimeError("placement failed")

    with patch.object(receipts_module, "_posting_thread", broken):
        unplaced = buy()
        assert (await service.execute(owner_id, unplaced, gold_lease)).status == "confirmed"
    async with db.sessions() as session:
        journal = await session.get(TradingJournalRow, unplaced.operation_id)
        assert journal is not None and journal.status == "confirmed"
    kept = await receipt(db, unplaced.operation_id)
    # Shown in Lonora's conversation rather than nowhere; still the agent's operation.
    assert kept.thread_id == threads["lonora"] and kept.agent_id == gold_id
    print("PASS a placement failure keeps the confirmation and its one receipt")

    # 9. Deleting the conversation, then the agent, keeps the receipt (3.1.2).
    async with db.sessions() as session, session.begin():
        await session.execute(delete(ThreadRow).where(ThreadRow.id == threads["gold"]))
    kept = await receipt(db, full.operation_id)
    assert kept.thread_id is None and kept.agent_id == gold_id
    async with db.sessions() as session, session.begin():
        await session.execute(delete(RunRow).where(RunRow.agent_id == gold_id))
        await session.execute(delete(AgentRow).where(AgentRow.id == gold_id))
    kept = await receipt(db, full.operation_id)
    assert kept.agent_id == gold_id
    async with db.sessions() as session:
        journal = await session.get(TradingJournalRow, full.operation_id)
        assert journal is not None and journal.status == "confirmed"
    print("PASS deleting the conversation and the agent keeps the receipt and its journal row")
    await db.close()


async def crash_after_send() -> None:
    db = database()
    broker = CrashAfterSendBroker(Path(sys.argv[4]))
    manager = cast(BrokerManager, ScriptedManager(broker))
    await ExecutionService(db, manager).execute(
        sys.argv[2], TradeRequest.model_validate_json(sys.argv[3])
    )
    raise AssertionError("Scripted worker failed to terminate after send")


if __name__ == "__main__":
    asyncio.run(crash_after_send() if len(sys.argv) > 1 else checks())
