"""Financial execution integrity and recovery on disposable PostgreSQL with the simulation broker.

Exercises crash-before-send recovery, interruption after submission (Owner addendum §6
step 7), scoped blocking against reduce-only admission under Emergency Stop, Trading OFF
and degraded/disconnected recovery, owner attestation through the authenticated API,
target-state reconciliation of modify/cancel operations, verification rechecks and the
approval batch stop. No live broker, MetaApi key or real order is involved.
"""

import asyncio
import os
import sys
from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.brokers.base import BrokerManager
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest, TradeResult, TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import BrokerSessionRow, EventRow, TradingAccountRow, TradingJournalRow
from lonora_db.trading_journal import persist_result, release_reservation
from lonora_tools.loader import load_tools
from lonora_trading.broker_recovery import reconcile_broker_account
from lonora_trading.controls import read_controls, save_controls
from lonora_trading.execution import ExecutionService
from lonora_trading.reconciliation import (
    recheck_verifications,
    reconcile_ambiguous,
    send_lock_key,
)
from sqlalchemy import delete, select, text

GOLD, EURO, POUND = "XAUUSD.r", "EURUSD.r", "GBPUSD.r"


class CrashingSimulation(SimulationBroker):
    """A worker process killed at an exact point of the send path (child process only)."""

    def __init__(self, db: Database, owner_id: str, connection_id: str, mode: str):
        super().__init__(db, owner_id, connection_id)
        self.mode = mode

    async def execute(
        self, request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        if self.mode == "before-send":
            os._exit(25)  # Reserved, never authorized: provably not sent.
        if self.mode == "after-boundary":
            assert before_send is not None
            await before_send()
            os._exit(24)  # Authorized, killed before the broker effect.
        await super().execute(request, before_send)
        os._exit(23)  # Broker effect committed, acknowledgement never returned.


class SingleBroker:
    def __init__(self, broker: Any):
        self.broker = broker

    async def get(self, owner_id: str, connection_id: str) -> Any:
        return self.broker


class LossyBroker(SimulationBroker):
    """Loses selected responses and, like MetaApi, has no correlated mutation evidence."""

    def __init__(self, db: Database, owner_id: str, connection_id: str):
        super().__init__(db, owner_id, connection_id)
        self.lose_after_effect: set[str] = set()
        self.lose_before_effect: set[str] = set()
        self.lose_next_close = False
        self.sent: list[str] = []
        self.reconciled: list[str] = []
        self.waiting = asyncio.Event()
        self.release: asyncio.Event | None = None
        # Operation -> gate: cross the send boundary, wait, then report a broker rejection.
        self.reject_after_boundary: dict[str, asyncio.Event] = {}
        self.boundary = asyncio.Event()

    async def execute(
        self, request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        if self.release is not None:
            self.waiting.set()
            await self.release.wait()
        if request.operation_id in self.lose_before_effect:
            assert before_send is not None
            await before_send()
            self.sent.append(request.operation_id)
            raise TimeoutError("explicit response loss before the simulated effect")
        if request.operation_id in self.reject_after_boundary:
            assert before_send is not None
            await before_send()
            self.sent.append(request.operation_id)
            self.boundary.set()
            await self.reject_after_boundary[request.operation_id].wait()
            return TradeResult(
                operation_id=request.operation_id, status="failed", code="market_closed"
            )
        result = await super().execute(request, before_send)
        self.sent.append(request.operation_id)
        if request.operation_id in self.lose_after_effect or (
            self.lose_next_close and request.action == "close_position"
        ):
            self.lose_next_close = False
            raise TimeoutError("explicit response loss after the simulated effect")
        return result

    async def reconcile(
        self,
        operation_id: str,
        request: TradeRequest | None = None,
        *,
        submitted_at: Any = None,
    ) -> TradeResult:
        self.reconciled.append(operation_id)
        if request and request.action in {"modify_order", "modify_position", "cancel_order"}:
            return TradeResult(
                operation_id=operation_id, status="ambiguous", code="mutation_evidence_required"
            )
        return await super().reconcile(operation_id, request, submitted_at=submitted_at)


class UnobservableBroker(SimulationBroker):
    """Correlated history and account reads keep failing (e.g. MetaApi broker_history_limit)."""

    def __init__(self, db: Database, owner_id: str, connection_id: str):
        super().__init__(db, owner_id, connection_id)
        self.reconciled: list[str] = []

    async def reconcile(
        self,
        operation_id: str,
        request: TradeRequest | None = None,
        *,
        submitted_at: Any = None,
    ) -> TradeResult:
        self.reconciled.append(operation_id)
        raise LonoraError("broker_history_limit", 409)

    async def execute(
        self, request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        raise AssertionError("Recovery must never send")


def instrument(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "digits": 2,
        "tick_size": "0.01",
        "volume_min": "0.1",
        "volume_max": "10",
        "volume_step": "0.1",
    }


def quote(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "bid": "100",
        "ask": "101",
        "observed_at": utcnow().isoformat(),
        "source": "explicit-recovery-fixture",
    }


async def main() -> None:
    fixture = await Fixture().open()
    db = fixture.runtime.db
    original_controls = await read_controls(db)
    connection_id: str | None = None
    operations: list[str] = []
    try:
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "recovery-" + uuid4().hex, "enabled": True},
        )
        connection_id = cast(str, connection["id"])
        await fixture.request(
            "POST",
            f"/trading/connections/{connection_id}/simulation",
            {
                "snapshot": {
                    "currency": "USD",
                    "balance": "10000",
                    "instruments": [instrument(s) for s in (GOLD, EURO, POUND)],
                    "quotes": {s: quote(s) for s in (GOLD, EURO, POUND)},
                }
            },
        )
        await save_controls(db, TradingControl(enabled=True))
        services = fixture.runtime.services(fixture.owner)
        service = services.trading
        broker = cast(SimulationBroker, await services.brokers.get(fixture.owner, connection_id))
        account = connection_id

        async def refresh() -> None:
            async with db.sessions() as session, session.begin():
                row = await session.get(TradingAccountRow, account, with_for_update=True)
                assert row is not None
                row.payload = {**row.payload, "quotes": {s: quote(s) for s in (GOLD, EURO, POUND)}}

        def trade(action: str, symbol: str = GOLD, **fields: Any) -> TradeRequest:
            operation = "recovery-" + uuid4().hex
            operations.append(operation)
            return TradeRequest.model_validate(
                {
                    "account_id": account,
                    "operation_id": operation,
                    "action": action,
                    "symbol": symbol,
                    **fields,
                }
            )

        async def run(request: TradeRequest) -> TradeResult:
            await refresh()
            return await service.execute(fixture.owner, request)

        async def blocked(request: TradeRequest, code: str) -> None:
            try:
                await run(request)
            except LonoraError as error:
                assert error.code == code, (error.code, code)
            else:
                raise AssertionError("Expected " + code + " for " + request.action)
            async with db.sessions() as session:
                assert await session.get(TradingJournalRow, request.operation_id) is None

        async def journal(operation_id: str) -> TradingJournalRow:
            async with db.sessions() as session:
                row = await session.get(TradingJournalRow, operation_id)
                assert row is not None
                return row

        async def backdate(operation_id: str, delta: timedelta, *, attempt: bool = False) -> None:
            async with db.sessions() as session, session.begin():
                row = await session.get(TradingJournalRow, operation_id, with_for_update=True)
                assert row is not None and row.submitted_at is not None
                row.submitted_at -= delta
                if attempt:
                    row.updated_at -= delta

        async def events(kind: str, operation_id: str) -> list[dict[str, Any]]:
            async with db.sessions() as session:
                rows = await session.scalars(
                    select(EventRow)
                    .where(
                        EventRow.kind == kind,
                        EventRow.payload["operation_id"].as_string() == operation_id,
                    )
                    .order_by(EventRow.cursor)
                )
                return [row.payload for row in rows]

        async def operations_at_broker() -> dict[str, Any]:
            return dict((await broker.snapshot()).get("operations", {}))

        async def child(mode: str, request: TradeRequest) -> int:
            process = await asyncio.create_subprocess_exec(
                sys.executable,
                __file__,
                mode,
                fixture.owner,
                account,
                request.model_dump_json(),
            )
            return await asyncio.wait_for(process.wait(), 60)

        opened: dict[str, str] = {}
        opened_by: dict[str, str] = {}
        for name, request in (
            ("p1", trade("buy", volume="1", stop_loss="95", take_profit="110")),
            ("p2", trade("buy", volume="0.5", stop_loss="95", take_profit="110")),
            ("p3", trade("buy", EURO, volume="0.3", stop_loss="95")),
            ("o1", trade("buy_limit", volume="0.2", price="99")),
            ("o2", trade("buy_limit", volume="0.2", price="98")),
        ):
            result = await run(request)
            assert result.status == "confirmed" and result.broker_id, result
            assert result.details["verification"]["status"] == "verified"
            opened[name] = result.broker_id
            opened_by[name] = request.operation_id
            updates = await events("trading.operation_updated", request.operation_id)
            assert [item["send_state"] for item in updates][:1] == ["sent"]
            assert updates[-1]["status"] == "confirmed"

        # 1. Owner addendum §6 step 7: interrupted after submission, before acknowledgement.
        await refresh()
        after_effect = trade("buy", volume="0.1", stop_loss="95")
        assert await child("after-effect", after_effect) == 23
        row = await journal(after_effect.operation_id)
        assert row.status == "submitted" and row.request["symbol"] == GOLD
        assert row.result["details"]["execution"]["send_authorized"] is True
        positions_before = len(await broker.positions())
        assert after_effect.operation_id in await operations_at_broker()
        await backdate(after_effect.operation_id, timedelta(minutes=2))
        assert await reconcile_ambiguous(db, services.brokers) == 1
        row = await journal(after_effect.operation_id)
        broker_receipt = (await operations_at_broker())[after_effect.operation_id]
        assert row.status == "confirmed" and row.result["broker_id"] == broker_receipt["broker_id"]
        replay = await service.execute(fixture.owner, after_effect)
        assert replay.status == "confirmed"
        assert len(await broker.positions()) == positions_before
        assert list(await operations_at_broker()).count(after_effect.operation_id) == 1
        print(
            "PASS interrupted after submit before acknowledgement stays traceable as submitted and recovery confirms it from broker evidence without resending"
        )

        # 2. Crash before the send boundary: provably never sent, released without the broker.
        await refresh()
        before_send = trade("buy", volume="0.1", stop_loss="95")
        assert await child("before-send", before_send) == 25
        row = await journal(before_send.operation_id)
        assert row.status == "reserved"
        # A reservation does not block the market: it never crossed the send boundary.
        unblocked = trade("buy", volume="0.1", stop_loss="95")
        assert (await run(unblocked)).status == "confirmed"
        opened["p4"] = (await journal(unblocked.operation_id)).result["broker_id"]
        lossy = LossyBroker(db, fixture.owner, account)
        cached = services.brokers.connections[account]
        services.brokers.connections[account] = (cached[0], lossy)
        await backdate(before_send.operation_id, timedelta(minutes=6), attempt=True)
        assert await reconcile_ambiguous(db, services.brokers) == 1
        row = await journal(before_send.operation_id)
        assert row.status == "failed" and row.result["code"] == "operation_not_sent"
        assert row.result["details"]["send_state"] == "not_sent"
        assert before_send.operation_id not in lossy.reconciled
        assert before_send.operation_id not in await operations_at_broker()
        assert (await events("trading.operation_updated", before_send.operation_id))[-1][
            "send_state"
        ] == "not_sent"
        # A late sender of a released reservation stops at the send boundary.
        late = trade("buy", volume="0.1", stop_loss="95")
        lossy.release = asyncio.Event()
        await refresh()
        pending = asyncio.create_task(service.execute(fixture.owner, late))
        await asyncio.wait_for(lossy.waiting.wait(), 10)
        async with db.sessions() as session, session.begin():
            assert await release_reservation(session, late.operation_id, "fixture") is not None
        lossy.release.set()
        result = await asyncio.wait_for(pending, 30)
        lossy.release = None
        assert result.status == "failed" and result.details["send_state"] == "not_sent"
        assert late.operation_id not in lossy.sent
        assert late.operation_id not in await operations_at_broker()
        print(
            "PASS a reservation killed before the send boundary resolves to failed(not_sent) with no broker call, never blocks its market, and a late sender cannot cross the boundary"
        )

        # 3. Authorized but killed before the broker effect: uncertain, never resent.
        services.brokers.connections[account] = cached
        await refresh()
        unknown = trade("buy", volume="0.1", stop_loss="95")
        assert await child("after-boundary", unknown) == 24
        await backdate(unknown.operation_id, timedelta(minutes=2))
        assert await reconcile_ambiguous(db, services.brokers) == 0
        row = await journal(unknown.operation_id)
        assert (
            row.status == "ambiguous" and row.result["code"] == "execution_interrupted_after_send"
        )
        assert unknown.operation_id not in await operations_at_broker()

        # Scoped blocking: new risk on the affected market only.
        await blocked(trade("buy", volume="0.1", stop_loss="95"), "broker_reconciliation_required")
        await blocked(
            trade("modify_order", order_id=opened["o1"], price="99.5"),
            "broker_reconciliation_required",
        )
        assert (await run(trade("buy", EURO, volume="0.1", stop_loss="95"))).status == "confirmed"
        # Reduce-only stays admissible under Emergency Stop, even on the uncertain market.
        await save_controls(db, TradingControl(emergency_stop=True))
        partial = await run(trade("close_position", position_id=opened["p1"], volume="0.4"))
        assert partial.status == "confirmed"
        assert partial.details["execution"]["risk_reducing"] is True
        tightened = await run(trade("modify_position", position_id=opened["p2"], stop_loss="97"))
        assert tightened.status == "confirmed"
        await blocked(
            trade("modify_position", position_id=opened["p2"], stop_loss="90"), "emergency_stop"
        )
        await blocked(
            trade("modify_position", position_id=opened["p2"], take_profit="120"), "emergency_stop"
        )
        assert (await run(trade("cancel_order", order_id=opened["o1"]))).status == "confirmed"
        await blocked(trade("buy", EURO, volume="0.1", stop_loss="95"), "emergency_stop")
        await save_controls(db, TradingControl(enabled=False))
        assert (
            await run(trade("modify_position", position_id=opened["p1"], stop_loss="96"))
        ).status == "confirmed"
        await blocked(trade("buy", POUND, volume="0.1", stop_loss="95"), "trading_disabled")
        await save_controls(db, TradingControl(enabled=True))
        print(
            "PASS an unresolved operation blocks new risk on its market only; closes, tighter stops and cancels stay admissible under Emergency Stop and Trading OFF"
        )

        # Degraded account observation is scoped; a disconnected one blocks new risk only.
        snapshot = await reconcile_broker_account(db, services.brokers, fixture.owner, account)
        assert snapshot is not None and snapshot.status == "degraded"
        assert unknown.operation_id in snapshot.unresolved_operations
        assert (await run(trade("buy", POUND, volume="0.1", stop_loss="95"))).status == "confirmed"
        await blocked(trade("buy", volume="0.1", stop_loss="95"), "broker_reconciliation_required")

        async def recovery_status(status: str) -> None:
            async with db.sessions() as session, session.begin():
                row = await session.get(BrokerSessionRow, account, with_for_update=True)
                assert row is not None
                row.state = {
                    **row.state,
                    "broker_recovery": {**row.state["broker_recovery"], "status": status},
                }

        await recovery_status("disconnected")
        await blocked(
            trade("buy", POUND, volume="0.1", stop_loss="95"), "broker_reconciliation_required"
        )
        assert (
            await run(trade("close_position", EURO, position_id=opened["p3"]))
        ).status == "confirmed"
        await recovery_status("degraded")
        print(
            "PASS degraded recovery blocks only markets with unresolved operations; a disconnected observation blocks new risk but still admits closing"
        )

        # 4. Owner attestation through the authenticated API: audited, history retained.
        path = f"/api/trading/journal/{unknown.operation_id}/resolve"
        body = {
            "outcome": "not_executed",
            "statement": "Checked the broker terminal: no order for this request.",
            "broker_reference": "terminal-history-check",
        }
        forged = await fixture.client.post(path, json=body, headers={"X-CSRF-Token": "invalid"})
        assert forged.status_code == 403 and forged.json()["code"] == "csrf_required"
        assert (await journal(unknown.operation_id)).status == "ambiguous"
        resolved = await fixture.request("POST", path.removeprefix("/api"), body)
        assert resolved["status"] == "resolved" and resolved["send_state"] == "sent"
        resolution = resolved["result"]["details"]["resolution"]
        assert resolution["source"] == "owner" and resolution["outcome"] == "not_executed"
        assert resolution["actor"]["owner_id"] == fixture.owner
        assert resolution["broker_confirmed"] is False and resolution["broker_reference"]
        assert resolved["result"]["details"]["prior_receipt"]["code"] == (
            "execution_interrupted_after_send"
        )
        assert resolved["result"]["details"]["execution_evidence"]["before_send"]
        assert resolved["request"] == unknown.model_dump(mode="json")
        audit = await events("trading.operation_resolved", unknown.operation_id)
        assert len(audit) == 1 and audit[0]["actor"]["owner_id"] == fixture.owner
        again = await fixture.client.post(path, json=body)
        assert again.status_code == 409 and again.json()["code"] == "operation_already_settled"
        settled = await fixture.client.post(
            f"/api/trading/journal/{after_effect.operation_id}/resolve", json=body
        )
        assert settled.status_code == 409
        missing = await fixture.client.post("/api/trading/journal/missing-op/resolve", json=body)
        assert missing.status_code == 404
        async with db.sessions() as session, session.begin():
            assert not await persist_result(
                session,
                unknown.operation_id,
                "ambiguous",
                TradeResult(operation_id=unknown.operation_id, status="ambiguous").model_dump(
                    mode="json"
                ),
            )
        assert (await run(trade("buy", volume="0.1", stop_loss="95"))).status == "confirmed"
        print(
            "PASS owner attestation is session-authenticated, audited and terminal, retains the original evidence, and clears the market block"
        )

        # 4b. A submission whose broker evidence stays unavailable is still owner-resolvable.
        async def stale_attempt(operation_id: str) -> None:
            async with db.sessions() as session, session.begin():
                row = await session.get(TradingJournalRow, operation_id, with_for_update=True)
                assert row is not None
                row.updated_at = utcnow() - timedelta(minutes=2)

        await refresh()
        unobservable = trade("buy", EURO, volume="0.1", stop_loss="95")
        assert await child("after-boundary", unobservable) == 24
        await backdate(unobservable.operation_id, timedelta(minutes=30), attempt=True)
        # While the account send lock is held a sender may still be inside its send:
        # nothing is concluded, leased or not.
        async with db.sessions() as holder, holder.begin():
            await holder.execute(
                text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
                {"key": send_lock_key(fixture.owner, account)},
            )
            await reconcile_ambiguous(db, services.brokers)
            assert (await journal(unobservable.operation_id)).status == "submitted"
        blind = UnobservableBroker(db, fixture.owner, account)
        services.brokers.connections[account] = (cached[0], blind)
        for _ in range(3):
            await stale_attempt(unobservable.operation_id)
            await reconcile_ambiguous(db, services.brokers)
        row = await journal(unobservable.operation_id)
        assert row.status == "ambiguous", row.status
        assert row.result["code"] == "execution_interrupted_after_send"
        assert unobservable.operation_id in blind.reconciled
        services.brokers.connections[account] = cached
        assert unobservable.operation_id not in await operations_at_broker()
        await blocked(
            trade("buy", EURO, volume="0.1", stop_loss="95"), "broker_reconciliation_required"
        )
        resolved = await fixture.request(
            "POST",
            f"/trading/journal/{unobservable.operation_id}/resolve",
            {
                "outcome": "not_executed",
                "statement": "Broker history unavailable; terminal shows none.",
            },
        )
        assert resolved["status"] == "resolved"
        assert (await run(trade("buy", EURO, volume="0.1", stop_loss="95"))).status == "confirmed"
        print(
            "PASS a crashed submission whose broker observation keeps failing becomes ambiguous once its send lock is free, so the owner can resolve it and unblock its market"
        )

        # 4c. Final outcomes are persisted under the account send lock: a sibling on the same
        # market waits for a definitive rejection and proceeds, instead of a spurious block.
        services.brokers.connections[account] = (cached[0], lossy)
        gate = asyncio.Event()
        rejected = trade("buy", POUND, volume="0.1", stop_loss="95")
        sibling = trade("buy", POUND, volume="0.1", stop_loss="95")
        lossy.reject_after_boundary[rejected.operation_id] = gate
        await refresh()
        first = asyncio.create_task(service.execute(fixture.owner, rejected))
        await asyncio.wait_for(lossy.boundary.wait(), 10)
        assert (await journal(rejected.operation_id)).status == "submitted"
        second = asyncio.create_task(service.execute(fixture.owner, sibling))
        waiting: TradingJournalRow | None = None
        for _ in range(200):
            async with db.sessions() as session:
                waiting = await session.get(TradingJournalRow, sibling.operation_id)
            if waiting is not None:
                break
            await asyncio.sleep(0.05)
        # Admitted while the sibling is only in flight; now waiting for the send lock.
        assert waiting is not None and waiting.status == "reserved" and not second.done()

        async def slow_persist(session: Any, operation_id: str, *args: Any) -> bool:
            if operation_id == rejected.operation_id:
                await asyncio.sleep(1)  # Widen the window between broker reply and journal.
            return await persist_result(session, operation_id, *args)

        with patch("lonora_trading.execution.persist_result", slow_persist):
            gate.set()
            first_result = await asyncio.wait_for(first, 30)
        assert first_result.status == "failed" and first_result.code == "market_closed"
        second_result = await asyncio.wait_for(second, 30)
        assert second_result.status == "confirmed", second_result
        assert lossy.sent.count(rejected.operation_id) == 1
        services.brokers.connections[account] = cached
        print(
            "PASS a definitive rejection is persisted under the account send lock, so a sibling on the same market proceeds instead of failing broker_reconciliation_required"
        )

        # 5. Modify/cancel conclude from the broker target, never by resending.
        services.brokers.connections[account] = (cached[0], lossy)
        tighter = trade("modify_position", position_id=opened["p2"], stop_loss="98")
        lossy.lose_after_effect.add(tighter.operation_id)
        assert (await run(tighter)).status == "ambiguous"
        await backdate(tighter.operation_id, timedelta(minutes=3))
        assert await reconcile_ambiguous(db, services.brokers) == 1
        row = await journal(tighter.operation_id)
        assert row.status == "confirmed" and row.result["code"] == "target_state_matches"
        target = trade("modify_position", position_id=opened["p2"], take_profit="112")
        lossy.lose_before_effect.add(target.operation_id)
        assert (await run(target)).status == "ambiguous"
        await backdate(target.operation_id, timedelta(minutes=3))
        assert await reconcile_ambiguous(db, services.brokers) == 1
        row = await journal(target.operation_id)
        assert row.status == "failed" and row.result["code"] == "target_state_not_reached"
        cancel = trade("cancel_order", order_id=opened["o2"])
        lossy.lose_after_effect.add(cancel.operation_id)
        assert (await run(cancel)).status == "ambiguous"
        assert await reconcile_ambiguous(db, services.brokers) == 0  # Inside the settle window.
        await backdate(cancel.operation_id, timedelta(minutes=3))
        assert await reconcile_ambiguous(db, services.brokers) == 1
        row = await journal(cancel.operation_id)
        assert row.status == "confirmed" and row.result["code"] == "order_no_longer_pending"
        for operation in (tighter.operation_id, target.operation_id, cancel.operation_id):
            assert lossy.sent.count(operation) == 1
        print(
            "PASS modify/cancel operations conclude by comparing the observed target with the requested change after the settle window, with exactly one send each"
        )

        # 6. Pending state verification is rechecked by the maintenance loop.
        verified_op = trade("buy", POUND, volume="0.2", stop_loss="95")
        assert (await run(verified_op)).status == "confirmed"
        stale_op = opened_by["p1"]
        for operation, age in ((verified_op.operation_id, 1), (stale_op, 20)):
            async with db.sessions() as session, session.begin():
                row = await session.get(TradingJournalRow, operation, with_for_update=True)
                assert row is not None
                details = row.result["details"]
                row.result = {
                    **row.result,
                    "details": {
                        **details,
                        "verification": {
                            **details["verification"],
                            "status": "pending",
                            "code": "broker_state_not_yet_verified",
                            "observed_at": (utcnow() - timedelta(minutes=age)).isoformat(),
                        },
                    },
                }
                row.updated_at = utcnow() - timedelta(minutes=1)
        assert await recheck_verifications(db, services.brokers) == 2
        verification = (await journal(verified_op.operation_id)).result["details"]["verification"]
        assert verification["status"] == "verified" and verification["attempts"] == 2
        # p1 was partially closed since, so its original fill can no longer be matched.
        verification = (await journal(stale_op)).result["details"]["verification"]
        assert verification["status"] == "unverified"
        assert verification["code"] == "broker_state_not_verified_in_window"
        assert (await journal(stale_op)).status == "confirmed"
        assert (await events("trading.operation_updated", verified_op.operation_id))[-1][
            "verification_status"
        ] == "verified"
        print(
            "PASS pending broker-state verification is rechecked until verified, or ends unverified after the window without changing the confirmed receipt"
        )

        # 7. The approval path stops a batch after a non-confirmed result.
        agent = await fixture.agent("Recovery batch", supervised=True)
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        registry = load_tools()
        await refresh()
        gold = sorted(p.id for p in await broker.positions() if p.symbol == GOLD)
        assert len(gold) >= 3
        # Proposed through the tool_call bridge, as a model without the native schema
        # would: resolution yields the exact direct call, so the approval card, its
        # call identity and the batch stop below are the same as for a direct call.
        identity = "batch-" + uuid4().hex
        arguments = {"account_id": account, "symbol": GOLD}
        call = registry.resolve_call(
            ToolCall(
                id=identity,
                name="tool_call",
                arguments={"name": "trade_close_positions", "arguments": arguments},
            )
        )
        assert call == ToolCall(id=identity, name="trade_close_positions", arguments=arguments)
        proposal = await registry.execute(call, context)
        await fixture.request(
            "POST",
            f"/trading/approvals/{proposal['approval_id']}/decision",
            {"decision": "approve"},
        )
        lossy.lose_next_close = True
        sent_before = len(lossy.sent)
        await refresh()
        outcome = await registry.execute(call, context)
        results = outcome["results"]
        operations.extend(item["operation_id"] for item in results)
        assert len(results) == len(gold) and results[0]["status"] == "ambiguous"
        assert all(
            item["status"] == "failed"
            and item["code"] == "batch_halted_after_unconfirmed_result"
            and item["details"]["send_state"] == "not_sent"
            for item in results[1:]
        )
        assert len(lossy.sent) == sent_before + 1
        remaining = sorted(p.id for p in await broker.positions() if p.symbol == GOLD)
        assert remaining == gold[1:]
        for item in results[1:]:
            async with db.sessions() as session:
                assert await session.get(TradingJournalRow, item["operation_id"]) is None
        services.brokers.connections[account] = cached
        print(
            "PASS an approved batch (proposed through the tool_call bridge) stops after an uncertain result and reports the rest as never sent"
        )

        # 8. Approved cards (the supervised agent path) under Emergency Stop and Trading OFF:
        # exits stay admissible on the still-uncertain GOLD market, new risk never is.
        async def approved(arguments: dict[str, Any]) -> dict[str, Any]:
            call = ToolCall(
                id="card-" + uuid4().hex,
                name="trade_execute",
                arguments={"account_id": account, **arguments},
            )
            proposal = await registry.execute(call, context)
            assert proposal["_runtime_wait"], proposal
            await fixture.request(
                "POST",
                f"/trading/approvals/{proposal['approval_id']}/decision",
                {"decision": "approve"},
            )
            await refresh()
            outcome = await registry.execute(call, context)
            operations.extend(item["operation_id"] for item in outcome["results"])
            return outcome

        assert (await journal(results[0]["operation_id"])).status == "ambiguous"
        resting = await run(trade("buy_limit", POUND, volume="0.2", price="99"))
        assert resting.status == "confirmed" and resting.broker_id
        await refresh()
        held = sorted(
            (p for p in await broker.positions() if p.symbol == GOLD and p.stop_loss),
            key=lambda p: p.id,
        )
        assert len(held) >= 2
        stops = [p.stop_loss or Decimal(0) for p in held]
        await save_controls(db, TradingControl(emergency_stop=True))
        tightened = await approved(
            {
                "action": "modify_position",
                "symbol": GOLD,
                "position_id": held[0].id,
                "stop_loss": str(stops[0] + Decimal("0.5")),
            }
        )
        assert tightened["status"] == "confirmed", tightened
        assert tightened["details"]["execution"]["risk_reducing"] is True
        assert tightened["details"]["execution"]["run_id"] == context.lease.run_id
        entry = await approved(
            {"action": "buy", "symbol": EURO, "volume": "0.1", "stop_loss": "95"}
        )
        assert entry["status"] == "failed" and entry["code"] == "emergency_stop", entry
        widened = await approved(
            {
                "action": "modify_position",
                "symbol": GOLD,
                "position_id": held[1].id,
                "stop_loss": str(stops[1] - Decimal("1")),
            }
        )
        assert widened["status"] == "failed" and widened["code"] == "emergency_stop", widened
        await save_controls(db, TradingControl(enabled=False))
        closed = await approved(
            {"action": "close_position", "symbol": GOLD, "position_id": held[1].id}
        )
        assert closed["status"] == "confirmed", closed
        assert not any(p.id == held[1].id for p in await broker.positions())
        cancelled = await approved(
            {"action": "cancel_order", "symbol": POUND, "order_id": resting.broker_id}
        )
        assert cancelled["status"] == "confirmed", cancelled
        entry = await approved(
            {"action": "buy_limit", "symbol": POUND, "volume": "0.1", "price": "99"}
        )
        assert entry["status"] == "failed" and entry["code"] == "trading_disabled", entry
        await save_controls(db, TradingControl(enabled=True))
        print(
            "PASS approved agent cards close, cancel and tighten under Emergency Stop and Trading OFF on an uncertain market, while entries and wider stops stay blocked"
        )
    finally:
        await save_controls(db, original_controls)
        async with db.sessions() as session, session.begin():
            await session.execute(
                delete(TradingJournalRow).where(TradingJournalRow.operation_id.in_(operations))
            )
        if connection_id:
            await fixture.request("DELETE", "/trading/connections/" + connection_id)
        await fixture.close()


async def crash_child() -> None:
    mode, owner_id, connection_id, payload = sys.argv[1:5]
    db = Database.connect(os.environ["LONORA_DATABASE_URL"])
    broker = CrashingSimulation(db, owner_id, connection_id, mode)
    manager = cast(BrokerManager, SingleBroker(broker))
    await ExecutionService(db, manager).execute(owner_id, TradeRequest.model_validate_json(payload))
    raise SystemExit(99)  # The scripted worker failed to terminate at its crash point.


if __name__ == "__main__":
    asyncio.run(crash_child() if len(sys.argv) > 1 else main())
