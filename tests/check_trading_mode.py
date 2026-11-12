"""The trading mode at the real execution door on PostgreSQL (mandate 4.1, 4.2, 6.7).

Scripted broker only; no live orders. Run on a fresh disposable *_test database.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

from check_trading import ScriptedBroker, ScriptedManager, database
from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.account import Position
from lonora_contracts.agent_permissions import PermissionChange
from lonora_contracts.domain import utcnow
from lonora_contracts.runs import Lease
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_core.user_error import LonoraError
from lonora_db.agent_permissions import change_permission
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.schema import (
    AgentRow,
    OwnerRow,
    RunRow,
    ThreadRow,
    TradeApprovalRow,
    TradingJournalRow,
)
from lonora_db.trading_journal import persist_result, reserve_operation
from lonora_db.trading_mode import set_trading_mode, trading_mode
from lonora_trading.execution import ExecutionService
from lonora_trading.idempotency import trade_fingerprint
from lonora_trading.manual_activity import material_state
from sqlalchemy import select


async def checks() -> None:
    db = database()
    broker = ScriptedBroker()
    manager = cast(BrokerManager, ScriptedManager(broker))
    service = ExecutionService(db, manager)
    async with db.sessions() as session, session.begin():
        # One owner per install: reuse it when an earlier check in this database made it.
        owner = await session.scalar(select(OwnerRow))
        if owner is None:
            owner = OwnerRow(email="trading-mode@example.test", password_hash="not-a-fixture-login")
            session.add(owner)
            await session.flush()
        owner_id = owner.id
        account = await BrokerSessionRepository().create(
            session,
            owner_id,
            {"provider": "simulation", "account_id": "trading-mode-fixture", "enabled": True},
        )
        account_id = account.id
        agent = AgentRow(owner_id=owner_id, name="Gold")
        session.add(agent)
        await session.flush()
        agent_id = agent.id
        thread = ThreadRow(owner_id=owner_id, agent_id=agent_id)
        session.add(thread)
        await session.flush()
        run = RunRow(
            thread_id=thread.id,
            agent_id=agent_id,
            status="running",
            lease_owner="mode-worker",
            lease_fence=1,
            lease_expires_at=utcnow() + timedelta(minutes=5),
        )
        session.add(run)
        await session.flush()
        lease = Lease(run_id=run.id, owner="mode-worker", fence=1)
        # The ladder keeps working until it is removed; this agent is at "Ask me".
        await change_permission(
            session, owner_id, agent_id, PermissionChange(level="supervised", expected_revision=0)
        )
    broker.account_id = account_id
    broker.scripted_positions = [
        Position(
            id="mode-position",
            symbol="FIXTURE",
            side="buy",
            volume=Decimal("0.2"),
            open_price=Decimal("10"),
        ),
        # Opened in the broker terminal: the owner's own position.
        Position(
            id="owner-position",
            symbol="FIXTURE",
            side="buy",
            volume=Decimal("0.1"),
            open_price=Decimal("10"),
        ),
    ]
    # The agent's own journaled order opened mode-position.
    opening = TradeRequest(
        account_id=account_id,
        operation_id="mode-open-" + uuid4().hex,
        action="buy",
        symbol="FIXTURE",
        volume=Decimal("0.2"),
    )
    async with db.sessions() as session, session.begin():
        row, _ = await reserve_operation(
            session,
            owner_id,
            opening.operation_id,
            account_id,
            trade_fingerprint(opening),
            opening.model_dump(mode="json"),
        )
        # The attribution the door writes from the leased run at reservation.
        row.result = TradeResult(
            operation_id=opening.operation_id,
            status="reserved",
            details={"execution": {"agent_id": agent_id, "run_id": lease.run_id}},
        ).model_dump(mode="json")
        await persist_result(
            session,
            opening.operation_id,
            "confirmed",
            TradeResult(
                operation_id=opening.operation_id,
                status="confirmed",
                broker_id="mode-position",
                details={"position_id": "mode-position"},
            ).model_dump(mode="json"),
        )

    def buy() -> TradeRequest:
        return TradeRequest(
            account_id=account_id,
            operation_id="mode-" + uuid4().hex,
            action="buy",
            symbol="FIXTURE",
            volume=Decimal("0.1"),
        )

    async def journaled(operation_id: str) -> TradingJournalRow | None:
        async with db.sessions() as session:
            return await session.get(TradingJournalRow, operation_id)

    # A new agent starts in Ask (4.3); the stored default is the column's.
    async with db.sessions() as session:
        assert await trading_mode(session, owner_id, agent_id) == "ask"

    # Ask: a risk-increasing request without the owner's exact approval is never sent.
    refused = buy()
    try:
        await service.execute(owner_id, refused, lease)
        raise AssertionError("Ask sent a risk-increasing request without approval")
    except LonoraError as error:
        assert error.code == "trade_approval_required"
    assert broker.sent == 0 and await journaled(refused.operation_id) is None

    # Ask: a risk-reducing request needs no approval; the door classifies it itself.
    partial = TradeRequest(
        account_id=account_id,
        operation_id="mode-" + uuid4().hex,
        action="close_position",
        symbol="FIXTURE",
        position_id="mode-position",
        volume=Decimal("0.1"),
    )

    def captured(position_id: str) -> dict[str, Any]:
        return material_state(next(p for p in broker.scripted_positions if p.id == position_id))

    # Without the ticket the agent read, a close is not sent: nothing proves it is still
    # the ticket the agent decided on (6.6, fail closed).
    blind = await service.execute(owner_id, partial, lease)
    assert blind.status == "failed" and blind.code == "broker_state_changed", blind
    assert broker.sent == 0
    partial = partial.model_copy(update={"operation_id": "mode-" + uuid4().hex})
    result = await service.execute(
        owner_id, partial, lease, expected_target=captured("mode-position")
    )
    assert result.status == "confirmed" and broker.sent == 1, result

    def close_owner_position() -> TradeRequest:
        return TradeRequest(
            account_id=account_id,
            operation_id="mode-" + uuid4().hex,
            action="close_position",
            symbol="FIXTURE",
            position_id="owner-position",
        )

    # The owner's own position is not this agent's (3.3.4): refused.
    try:
        await service.execute(owner_id, close_owner_position(), lease)
        raise AssertionError("Ask closed the owner's own position")
    except LonoraError as error:
        assert error.code == "ticket_not_owned"
    assert broker.sent == 1

    # Only the owner's tap sets Full.
    async with db.sessions() as session, session.begin():
        try:
            await set_trading_mode(session, owner_id, agent_id, "full", by="agent")
            raise AssertionError("An agent set itself to Full")
        except LonoraError as error:
            assert error.code == "trading_mode_full_owner_only"
    async with db.sessions() as session, session.begin():
        assert await set_trading_mode(session, owner_id, agent_id, "full", by="owner_tap") == (
            "full"
        )

    # Full: the agent executes on its own, journaled and broker-verified as always.
    full = buy()
    result = await service.execute(owner_id, full, lease)
    assert result.status == "confirmed" and broker.sent == 2, result
    row = await journaled(full.operation_id)
    assert row is not None and row.status == "confirmed"
    # Full does not reach the owner's own position either.
    try:
        await service.execute(owner_id, close_owner_position(), lease)
        raise AssertionError("Full closed the owner's own position")
    except LonoraError as error:
        assert error.code == "ticket_not_owned"
    assert broker.sent == 2
    # With the owner's standing instruction to manage every position, it may (3.3.4).
    async with db.sessions() as session, session.begin():
        managing = await session.get(AgentRow, agent_id)
        assert managing is not None
        managing.manages_all_positions = True
    result = await service.execute(
        owner_id, close_owner_position(), lease, expected_target=captured("owner-position")
    )
    assert result.status == "confirmed" and broker.sent == 3, result
    broker.scripted_positions = broker.scripted_positions[:1]

    # The stale-target check covers a request without a card too (6.6): the agent read
    # its own position, then it changed (the owner moved the stop) before the send.
    read = material_state(broker.scripted_positions[0])
    broker.scripted_positions[0] = broker.scripted_positions[0].model_copy(
        update={"stop_loss": Decimal("9")}
    )
    stale = TradeRequest(
        account_id=account_id,
        operation_id="mode-" + uuid4().hex,
        action="modify_position",
        symbol="FIXTURE",
        position_id="mode-position",
        stop_loss=Decimal("8"),
    )
    result = await service.execute(owner_id, stale, lease, expected_target=read)
    assert result.status == "failed" and result.code == "broker_state_changed", result
    assert result.details.get("send_state") == "not_sent" and broker.sent == 3
    # Read again, the same change is decided on the ticket as it is now.
    fresh = stale.model_copy(update={"operation_id": "mode-" + uuid4().hex})
    current = material_state(broker.scripted_positions[0])
    result = await service.execute(owner_id, fresh, lease, expected_target=current)
    assert result.status == "confirmed" and broker.sent == 4, result

    # A switch to Ask that lands after planning and before send is decided under the new
    # mode: the door reads it under the authority lock at send (4.2.3).
    raced = buy()

    async def switch_to_ask() -> None:
        async with db.sessions() as session, session.begin():
            await set_trading_mode(session, owner_id, agent_id, "ask", by="agent")

    broker.before = switch_to_ask
    result = await service.execute(owner_id, raced, lease)
    broker.before = None
    assert result.status == "failed" and result.code == "trade_approval_required", result
    assert result.details.get("send_state") == "not_sent" and broker.sent == 4

    # The mode change waits for a send check that holds the lock, and vice versa.
    async with db.sessions() as session, session.begin():
        await set_trading_mode(session, owner_id, agent_id, "full", by="owner_tap")
    held = asyncio.Event()
    release = asyncio.Event()

    async def hold_lock() -> None:
        from lonora_db.authority_lock import authority_lock

        async with db.sessions() as session, session.begin():
            await authority_lock(session, agent_id)
            held.set()
            await release.wait()

    holder = asyncio.create_task(hold_lock())
    await held.wait()
    switching = asyncio.create_task(switch_to_ask())
    await asyncio.sleep(0.3)
    assert not switching.done(), "A mode change did not wait for the authority lock"
    release.set()
    await asyncio.gather(holder, switching)
    async with db.sessions() as session:
        assert await trading_mode(session, owner_id, agent_id) == "ask"

    # The owner's own order on Lonora's own path (3.3.4): journaled, with no agent. Its
    # position is the owner's in both modes; the agent's own position is still managed.
    async with db.sessions() as session, session.begin():
        managing = await session.get(AgentRow, agent_id)
        assert managing is not None
        managing.manages_all_positions = False
        leased = await session.get(RunRow, lease.run_id)
        assert leased is not None
        run_thread = leased.thread_id
    sent = broker.sent
    owner_order = buy()
    placed = await service.execute(owner_id, owner_order)
    assert placed.status == "confirmed" and broker.sent == sent + 1, placed
    row = await journaled(owner_order.operation_id)
    assert row is not None
    assert row.result["details"]["execution"]["agent_id"] is None, row.result
    broker.scripted_positions.append(
        Position(
            id="owner-order-position",
            symbol="FIXTURE",
            side="buy",
            volume=Decimal("0.1"),
            open_price=Decimal("10"),
            stop_loss=Decimal("9"),
            operation_id=owner_order.operation_id,
        )
    )

    def on_owner_order(**fields: Any) -> TradeRequest:
        return TradeRequest(
            account_id=account_id,
            operation_id="mode-" + uuid4().hex,
            symbol="FIXTURE",
            position_id="owner-order-position",
            **fields,
        )

    async def refused_on_owner_order(mode: str, requests: list[TradeRequest]) -> None:
        sent = broker.sent
        for request in requests:
            try:
                await service.execute(
                    owner_id, request, lease, expected_target=captured("owner-order-position")
                )
                raise AssertionError(mode + " acted on the owner's own order")
            except LonoraError as error:
                assert error.code == "ticket_not_owned", (mode, error.code)
            assert await journaled(request.operation_id) is None
        assert broker.sent == sent

    def tighten(position_id: str, stop_loss: str) -> TradeRequest:
        return TradeRequest(
            account_id=account_id,
            operation_id="mode-" + uuid4().hex,
            action="modify_position",
            symbol="FIXTURE",
            position_id=position_id,
            stop_loss=Decimal(stop_loss),
        )

    # Ask: the close is refused, and so is the stop removal, even with the owner's exact
    # approval of it; nothing reaches the broker.
    removal = on_owner_order(action="modify_position", clear_stop_loss=True)
    async with db.sessions() as session, session.begin():
        session.add(
            TradeApprovalRow(
                id=str(uuid4()),
                owner_id=owner_id,
                run_id=lease.run_id,
                thread_id=run_thread,
                agent_id=agent_id,
                call_id="owner-order-removal",
                broker_snapshot={},
                requests=[removal.model_dump(mode="json")],
                status="approved",
                results=[],
            )
        )
    await refused_on_owner_order("Ask", [on_owner_order(action="close_position"), removal])
    # The agent's own position is still managed in Ask: a tighter stop needs no card.
    sent = broker.sent
    result = await service.execute(
        owner_id,
        tighten("mode-position", "9.5"),
        lease,
        expected_target=captured("mode-position"),
    )
    assert result.status == "confirmed" and broker.sent == sent + 1, result

    async with db.sessions() as session, session.begin():
        assert await set_trading_mode(session, owner_id, agent_id, "full", by="owner_tap") == (
            "full"
        )
    # Full: the same, without any approval.
    await refused_on_owner_order(
        "Full",
        [
            on_owner_order(action="close_position"),
            on_owner_order(action="modify_position", clear_stop_loss=True),
        ],
    )
    # The agent's own entry and its management in Full: no card.
    sent = broker.sent
    entry = buy()
    result = await service.execute(owner_id, entry, lease)
    assert result.status == "confirmed" and broker.sent == sent + 1, result
    broker.scripted_positions.append(
        Position(
            id="full-position",
            symbol="FIXTURE",
            side="buy",
            volume=Decimal("0.1"),
            open_price=Decimal("10"),
            stop_loss=Decimal("9"),
            operation_id=entry.operation_id,
        )
    )
    result = await service.execute(
        owner_id,
        tighten("full-position", "9.5"),
        lease,
        expected_target=captured("full-position"),
    )
    assert result.status == "confirmed" and broker.sent == sent + 2, result

    # 6.6 in Full: without the ticket the agent read, a change is not sent (fail closed).
    sent = broker.sent
    blind = await service.execute(owner_id, tighten("full-position", "9.6"), lease)
    assert blind.status == "failed" and blind.code == "broker_state_changed", blind
    assert broker.sent == sent
    # The owner changes the ticket between the agent's observation and the send: the
    # owner's change wins and nothing is sent.
    read = captured("full-position")

    async def owner_intervenes() -> None:
        index = next(i for i, p in enumerate(broker.scripted_positions) if p.id == "full-position")
        broker.scripted_positions[index] = broker.scripted_positions[index].model_copy(
            update={"stop_loss": Decimal("9.3")}
        )

    broker.before = owner_intervenes
    changed = await service.execute(
        owner_id, tighten("full-position", "9.7"), lease, expected_target=read
    )
    broker.before = None
    assert changed.status == "failed" and changed.code == "broker_state_changed", changed
    assert changed.details.get("send_state") == "not_sent" and broker.sent == sent

    # 6.2 in Full: a broker rejection keeps the server's send attribution in the journal.
    async def broker_reject(
        request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        assert before_send
        await before_send()
        return TradeResult(operation_id=request.operation_id, status="failed", code="market_closed")

    rejected_request = buy()
    with patch.object(broker, "execute", side_effect=broker_reject):
        rejected = await service.execute(owner_id, rejected_request, lease)
    assert rejected.status == "failed" and rejected.code == "market_closed", rejected
    row = await journaled(rejected_request.operation_id)
    assert row is not None and row.result["details"]["execution"]["send_authorized"] is True
    assert row.result["details"]["execution"]["agent_id"] == agent_id

    # 6.3 and 6.4 in Full: a lost acknowledgement is ambiguous, a replay answers from the
    # journal and never resends, and the unresolved market blocks other new risk.
    lost = buy()
    broker.mode = "timeout"
    ambiguous = await service.execute(owner_id, lost, lease)
    broker.mode = "confirmed"
    assert ambiguous.status == "ambiguous", ambiguous
    assert broker.sent == sent + 1
    replayed = await service.execute(owner_id, lost, lease)
    assert replayed.status == "ambiguous" and broker.sent == sent + 1, replayed
    other = buy().model_copy(update={"volume": Decimal("0.2")})
    try:
        await service.execute(owner_id, other, lease)
        raise AssertionError("New risk was sent on a market with an unresolved operation")
    except LonoraError as error:
        assert error.code == "broker_reconciliation_required", error.code
    assert await journaled(other.operation_id) is None and broker.sent == sent + 1
    row = await journaled(lost.operation_id)
    assert row is not None and row.result["details"]["execution"]["agent_id"] == agent_id
    print("trading mode checks passed")


if __name__ == "__main__":
    asyncio.run(checks())
