"""Real disposable PostgreSQL journal tests with an explicitly scripted broker, no live orders."""

import asyncio
import os
import sys
from collections.abc import AsyncIterator, Awaitable, Callable
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any, cast
from uuid import uuid4

from lonora_adapter_kit.broker import BrokerAdapter
from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.account import AccountState, Order, Position
from lonora_contracts.domain import utcnow
from lonora_contracts.market import Candle, Instrument, Quote
from lonora_contracts.runs import Lease
from lonora_contracts.trading import TradeRequest, TradeResult, TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.client import Database
from lonora_db.schema import (
    AgentRow,
    BrokerSessionRow,
    OwnerRow,
    RunRow,
    ThreadRow,
    TradingJournalRow,
)
from lonora_db.trading_journal import persist_result, reserve_operation
from lonora_trading.controls import read_controls, save_controls
from lonora_trading.execution import ExecutionService
from lonora_trading.idempotency import trade_fingerprint
from lonora_trading.journal import journal_data
from lonora_trading.preflight import preflight
from lonora_trading.reconciliation import reconcile_ambiguous
from sqlalchemy import delete, select
from sqlalchemy.engine import make_url


class ScriptedBroker:
    """Fixtures only. These prices and balances never enter production adapters."""

    def __init__(self):
        self.sent = 0
        self.reconciled = 0
        self.receipts: dict[str, TradeResult] = {}
        self.before: Callable[[], Awaitable[None]] | None = None
        self.mode = "confirmed"
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()
        self.wrong_reconcile = False
        self.scripted_positions: list[Position] = []

    async def symbols(self) -> list[str]:
        return ["FIXTURE"]

    async def instrument(self, symbol: str) -> Instrument:
        return Instrument(
            symbol="FIXTURE",
            digits=2,
            tick_size=Decimal("0.01"),
            volume_min=Decimal("0.1"),
            volume_max=Decimal("10"),
            volume_step=Decimal("0.1"),
        )

    async def instruments(self) -> list[Instrument]:
        return [await self.instrument("FIXTURE")]

    def stream_candles(self, symbol: str, timeframe: str) -> AsyncIterator[Candle]:
        raise NotImplementedError("Scripted trade fixture has no market stream")

    def stream_quotes(self, symbol: str) -> AsyncIterator[Quote]:
        raise NotImplementedError("Not needed by this scripted execution fixture")

    async def quote(self, symbol: str) -> Quote:
        return Quote(
            symbol="FIXTURE",
            bid=Decimal("100"),
            ask=Decimal("100.01"),
            observed_at=utcnow(),
            source="explicit-scripted-trading-fixture",
        )

    async def candles(self, symbol: str, timeframe: str, limit: int) -> list[Candle]:
        raise NotImplementedError("Not needed by this scripted execution fixture")

    async def account(self) -> AccountState:
        return AccountState(
            id="scripted",
            currency="USD",
            balance=Decimal(1000),
            equity=Decimal(1000),
            margin=Decimal(0),
            free_margin=Decimal(1000),
            observed_at=utcnow(),
        )

    async def history(self, start: datetime, end: datetime, limit: int) -> list[dict[str, Any]]:
        return []

    async def positions(self) -> list[Position]:
        return self.scripted_positions

    async def orders(self) -> list[Order]:
        return []

    async def execute(
        self, request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        if self.before:
            await self.before()
        assert before_send is not None
        await before_send()
        self.sent += 1
        result = TradeResult(
            operation_id=request.operation_id,
            status="confirmed",
            broker_id="scripted-order",
            details={"fixture": True, "order_id": "scripted-order", "deal_id": "scripted-deal"},
        )
        self.receipts[request.operation_id] = result
        if self.mode == "timeout":
            raise TimeoutError("Scripted response loss after send")
        if self.mode == "unexpected":
            raise RuntimeError("Scripted SDK failure after send")
        if self.mode == "cancel":
            self.waiting.set()
            await self.release.wait()
        if self.mode == "wrong_id":
            return result.model_copy(update={"operation_id": "unrelated-operation"})
        return result

    async def reconcile(
        self, operation_id: str, request: TradeRequest | None = None
    ) -> TradeResult:
        self.reconciled += 1
        if self.wrong_reconcile:
            return TradeResult(operation_id="unrelated-operation", status="confirmed")
        return self.receipts.get(operation_id) or TradeResult(
            operation_id=operation_id, status="ambiguous", code="execution_not_observed"
        )

    async def close(self) -> None:
        pass


class CrashAfterSendBroker(ScriptedBroker):
    def __init__(self, receipt_file: Path):
        super().__init__()
        self.receipt_file = receipt_file

    async def execute(
        self,
        request: TradeRequest,
        before_send: Callable[[], Awaitable[None]] | None = None,
    ) -> TradeResult:
        result = await super().execute(request, before_send)
        self.receipt_file.write_text(result.model_dump_json())
        # Simulate a killed worker after the broker effect, before journal completion.
        os._exit(23)


class ScriptedManager:
    def __init__(self, broker: ScriptedBroker):
        self.broker = broker

    async def get(self, owner_id: str, connection_id: str) -> BrokerAdapter:
        return self.broker


def database() -> Database:
    value = os.environ.get("LONORA_DATABASE_URL", "")
    url = make_url(value)
    if (
        not url.drivername.startswith("postgresql")
        or not (url.database or "").endswith("_test")
        or {"dbname", "database"}.intersection(key.lower() for key in url.query)
    ):
        raise SystemExit("Explicit disposable PostgreSQL *_test database required")
    return Database.connect(value)


async def checks() -> None:
    db = database()
    original_controls = await read_controls(db)
    accounts: list[str] = []
    operations: list[str] = []
    agent_id: str | None = None
    broker = ScriptedBroker()
    manager = cast(BrokerManager, ScriptedManager(broker))
    service = ExecutionService(db, manager)
    try:
        async with db.sessions() as session, session.begin():
            owner = await session.scalar(select(OwnerRow))
            if owner is None:
                owner = OwnerRow(
                    email="scripted-trading@example.test",
                    password_hash="not-an-authentication-fixture",
                )
                session.add(owner)
                await session.flush()
            owner_id = owner.id
            for _ in range(2):
                account = await BrokerSessionRepository().create(
                    session,
                    owner_id,
                    {
                        "provider": "simulation",
                        "account_id": "explicit-scripted-fixture",
                        "enabled": True,
                    },
                )
                accounts.append(account.id)
        await save_controls(db, TradingControl(enabled=True))

        def request(account: str | None = None) -> TradeRequest:
            operation_id = "scripted-" + uuid4().hex
            operations.append(operation_id)
            return TradeRequest(
                account_id=account or accounts[0],
                operation_id=operation_id,
                action="buy",
                symbol="FIXTURE",
                volume=Decimal("0.1"),
            )

        broker.scripted_positions = [
            Position(
                id="scripted-position",
                symbol="FIXTURE",
                side="buy",
                volume=Decimal("0.1"),
                open_price=Decimal("10"),
            )
        ]
        oversized_close = TradeRequest(
            account_id=accounts[0],
            action="close_position",
            symbol="FIXTURE",
            position_id="scripted-position",
            volume=Decimal("0.2"),
        )
        try:
            await preflight(broker, oversized_close)
            raise AssertionError("Oversized close reached broker submission")
        except LonoraError as error:
            assert error.code == "position_volume_exceeded"
        await preflight(broker, oversized_close.model_copy(update={"volume": Decimal("0.1")}))

        # Both contenders pass preflight; only one may cross the broker boundary.
        trade = request()
        results = await asyncio.gather(*(service.execute(owner_id, trade) for _ in range(8)))
        assert broker.sent == 1 and any(result.status == "confirmed" for result in results)
        replay = await ExecutionService(db, manager).execute(owner_id, trade)
        assert (
            replay.status == "confirmed"
            and replay.details["deal_id"] == "scripted-deal"
            and broker.sent == 1
        )
        try:
            await service.execute(owner_id, trade.model_copy(update={"volume": Decimal("0.2")}))
            raise AssertionError("Changed request reused immutable receipt")
        except LonoraError as error:
            assert error.code == "idempotency_conflict"

        assert replay.details["execution"]["provider"] == "simulation"
        assert replay.details["execution"]["broker_account_id"] == "explicit-scripted-fixture"
        async with db.sessions() as session:
            row = await session.get(TradingJournalRow, trade.operation_id)
            assert row is not None
            attributed = journal_data(row)
            assert attributed["provider"] == "simulation" and attributed["run_id"] is None
            assert row.request == trade.model_dump(mode="json")
            assert "secret_id" not in replay.details["execution"]

        # Race reservation across two account locks: same operation ID is global.
        raced = request()

        async def reserve(account: str) -> bool:
            candidate = raced.model_copy(update={"account_id": account})
            async with db.sessions() as session, session.begin():
                _, fresh = await reserve_operation(
                    session,
                    owner_id,
                    raced.operation_id,
                    account,
                    trade_fingerprint(candidate),
                    candidate.model_dump(mode="json"),
                )
                return fresh

        reserved = await asyncio.gather(
            *(reserve(account) for account in accounts), return_exceptions=True
        )
        assert sum(item is True for item in reserved) == 1
        assert any(
            isinstance(item, LonoraError) and item.code == "operation_id_conflict"
            for item in reserved
        )

        # Lost response remains uncertain across a new execution service; never blind retry.
        trade = request()
        broker.mode = "timeout"
        sent_before = broker.sent
        result = await service.execute(owner_id, trade)
        assert result.status == "ambiguous"
        await ExecutionService(db, manager).execute(owner_id, trade)
        assert broker.sent == sent_before + 1
        assert await reconcile_ambiguous(db, manager) == 1
        replay = await service.execute(owner_id, trade)
        assert replay.status == "confirmed" and broker.sent == sent_before + 1

        # Late uncertain responses cannot regress or contradict terminal evidence.
        async with db.sessions() as session, session.begin():
            changed = await persist_result(
                session,
                trade.operation_id,
                "ambiguous",
                TradeResult(operation_id=trade.operation_id, status="ambiguous").model_dump(
                    mode="json"
                ),
            )
            assert not changed
        assert (await service.execute(owner_id, trade)).status == "confirmed"

        # Exception and cancellation after irreversible send both retain uncertainty.
        broker.mode = "unexpected"
        failed_transport = request()
        assert (await service.execute(owner_id, failed_transport)).status == "ambiguous"
        broker.mode = "cancel"
        cancelled = request()
        task = asyncio.create_task(service.execute(owner_id, cancelled))
        await asyncio.wait_for(broker.waiting.wait(), 5)
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        async with db.sessions() as session:
            journal = await session.get(TradingJournalRow, cancelled.operation_id)
            assert journal is not None and journal.status == "ambiguous"
        broker.release.set()
        broker.mode = "confirmed"
        assert await reconcile_ambiguous(db, manager) == 2

        # Emergency-stop and account disable arriving during broker preparation block send.
        blocked = request()
        sent_before = broker.sent

        async def stop() -> None:
            await save_controls(db, TradingControl(emergency_stop=True))

        broker.before = stop
        result = await service.execute(owner_id, blocked)
        assert (
            result.status == "failed"
            and result.code == "emergency_stop"
            and broker.sent == sent_before
        )
        await save_controls(db, TradingControl(enabled=True))

        async def disable() -> None:
            async with db.sessions() as session, session.begin():
                account = await session.get(BrokerSessionRow, accounts[0], with_for_update=True)
                assert account is not None
                account.payload = {**account.payload, "enabled": False}
                account.version += 1

        broker.before = disable
        result = await service.execute(owner_id, request())
        assert (
            result.status == "failed"
            and result.code == "broker_disabled"
            and broker.sent == sent_before
        )
        async with db.sessions() as session, session.begin():
            account = await session.get(BrokerSessionRow, accounts[0], with_for_update=True)
            assert account is not None
            account.payload = {**account.payload, "enabled": True}
            account.version += 1
        broker.before = None

        # Mismatched broker receipt must never confirm the requested operation.
        broker.mode = "wrong_id"
        wrong = request()
        assert (await service.execute(owner_id, wrong)).status == "ambiguous"
        broker.wrong_reconcile = True
        assert await reconcile_ambiguous(db, manager) == 0
        assert (await service.execute(owner_id, wrong)).status == "ambiguous"
        broker.wrong_reconcile = False
        assert await reconcile_ambiguous(db, manager) == 1
        broker.mode = "confirmed"

        # A persisted submitted crash window is reconciled by observation, not resubmission.
        crashed = request()
        async with db.sessions() as session, session.begin():
            row, _ = await reserve_operation(
                session,
                owner_id,
                crashed.operation_id,
                crashed.account_id,
                trade_fingerprint(crashed),
                crashed.model_dump(mode="json"),
            )
            row.status = "submitted"
            row.submitted_at = utcnow() - timedelta(minutes=2)
        broker.receipts[crashed.operation_id] = TradeResult(
            operation_id=crashed.operation_id, status="confirmed", broker_id="scripted-crash-order"
        )
        sent_before = broker.sent
        assert (
            await ExecutionService(db, manager).execute(owner_id, crashed)
        ).status == "ambiguous"
        assert await reconcile_ambiguous(db, manager) == 1
        assert (
            await service.execute(owner_id, crashed)
        ).status == "confirmed" and broker.sent == sent_before

        # A real subprocess dies after durable scripted broker receipt but before DB result.
        killed = request()
        with TemporaryDirectory(prefix="lonora-scripted-broker-") as temporary:
            receipt_file = Path(temporary) / "receipt.json"
            child = await asyncio.create_subprocess_exec(
                sys.executable,
                __file__,
                "crash-after-send",
                owner_id,
                killed.model_dump_json(),
                str(receipt_file),
            )
            assert await asyncio.wait_for(child.wait(), 10) == 23
            observed = TradeResult.model_validate_json(receipt_file.read_text())
            async with db.sessions() as session, session.begin():
                row = await session.get(TradingJournalRow, killed.operation_id)
                assert row is not None and row.status == "submitted"
                row.submitted_at = utcnow() - timedelta(minutes=2)
            restarted = ScriptedBroker()
            restarted.receipts[killed.operation_id] = observed
            restarted_manager = cast(BrokerManager, ScriptedManager(restarted))
            restarted_service = ExecutionService(db, restarted_manager)
            assert (await restarted_service.execute(owner_id, killed)).status == "ambiguous"
            assert restarted.sent == 0
            assert await reconcile_ambiguous(db, restarted_manager) == 1
            result = await restarted_service.execute(owner_id, killed)
            assert result.status == "confirmed" and result.broker_id == observed.broker_id
            assert restarted.sent == 0

        # Fresh submissions and still-valid old worker leases are not stolen by observers.
        async with db.sessions() as session, session.begin():
            agent = AgentRow(owner_id=owner_id, name="Scripted trading lease")
            session.add(agent)
            await session.flush()
            agent_id = agent.id
            thread = ThreadRow(owner_id=owner_id, agent_id=agent.id)
            session.add(thread)
            await session.flush()
            run = RunRow(
                thread_id=thread.id,
                agent_id=agent.id,
                status="running",
                lease_owner="scripted-worker",
                lease_fence=1,
                lease_expires_at=utcnow() + timedelta(minutes=5),
            )
            session.add(run)
            await session.flush()
            lease = Lease(run_id=run.id, owner="scripted-worker", fence=1)
        fenced = request()

        async def invalidate() -> None:
            async with db.sessions() as session, session.begin():
                run = await session.get(RunRow, lease.run_id, with_for_update=True)
                assert run is not None
                run.lease_fence += 1

        broker.before = invalidate
        result = await service.execute(owner_id, fenced, lease)
        assert (
            result.status == "failed"
            and result.code == "stale_lease"
            and broker.sent == sent_before
        )
        assert result.details["execution"]["run_id"] == lease.run_id
        assert result.details["execution"]["agent_id"] == agent_id
        broker.before = None
        lease = lease.model_copy(update={"fence": 2})
        active = request()
        async with db.sessions() as session, session.begin():
            row, _ = await reserve_operation(
                session,
                owner_id,
                active.operation_id,
                active.account_id,
                trade_fingerprint(active),
                active.model_dump(mode="json"),
            )
            row.status = "submitted"
            row.submitted_at = utcnow() - timedelta(minutes=2)
            row.result = TradeResult(
                operation_id=active.operation_id,
                status="submitted",
                details={"lease": lease.model_dump()},
            ).model_dump(mode="json")
        broker.receipts[active.operation_id] = TradeResult(
            operation_id=active.operation_id, status="confirmed"
        )
        reconciled_before = broker.reconciled
        assert (
            await reconcile_ambiguous(db, manager) == 0 and broker.reconciled == reconciled_before
        )
        fresh_submission = request()
        async with db.sessions() as session, session.begin():
            row, _ = await reserve_operation(
                session,
                owner_id,
                fresh_submission.operation_id,
                fresh_submission.account_id,
                trade_fingerprint(fresh_submission),
                fresh_submission.model_dump(mode="json"),
            )
            row.status = "submitted"
            row.submitted_at = utcnow()
        broker.receipts[fresh_submission.operation_id] = TradeResult(
            operation_id=fresh_submission.operation_id, status="confirmed"
        )
        reconciled_before = broker.reconciled
        assert (
            await reconcile_ambiguous(db, manager) == 0 and broker.reconciled == reconciled_before
        )

        # Fifty unresolved older operations must not permanently starve newer evidence.
        async with db.sessions() as session, session.begin():
            for index in range(52):
                deferred = request()
                row, _ = await reserve_operation(
                    session,
                    owner_id,
                    deferred.operation_id,
                    deferred.account_id,
                    trade_fingerprint(deferred),
                    deferred.model_dump(mode="json"),
                )
                row.status = "ambiguous"
                row.submitted_at = utcnow() - timedelta(minutes=5)
                row.updated_at = utcnow() - timedelta(minutes=4) + timedelta(seconds=index)
                if index == 51:
                    broker.receipts[deferred.operation_id] = TradeResult(
                        operation_id=deferred.operation_id, status="confirmed"
                    )
        assert await reconcile_ambiguous(db, manager) == 0
        assert await reconcile_ambiguous(db, manager) == 1
        print(
            "Trading: 18 PostgreSQL/scripted-broker safety scenarios passed; no live broker calls"
        )
    finally:
        await save_controls(db, original_controls)
        async with db.sessions() as session, session.begin():
            await session.execute(
                delete(TradingJournalRow).where(TradingJournalRow.operation_id.in_(operations))
            )
            await session.execute(delete(BrokerSessionRow).where(BrokerSessionRow.id.in_(accounts)))
            if agent_id:
                await session.execute(delete(AgentRow).where(AgentRow.id == agent_id))
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
