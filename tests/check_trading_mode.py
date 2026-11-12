"""The trading mode at the real execution door on PostgreSQL (mandate 4.1, 4.2, 6.7).

Scripted broker only; no live orders. Run on a fresh disposable *_test database.
"""

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import cast
from uuid import uuid4

from check_trading import ScriptedBroker, ScriptedManager, database
from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.account import Position
from lonora_contracts.agent_permissions import PermissionChange
from lonora_contracts.domain import utcnow
from lonora_contracts.runs import Lease
from lonora_contracts.trading import TradeRequest, TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.agent_permissions import change_permission
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.schema import AgentRow, OwnerRow, RunRow, ThreadRow, TradingJournalRow
from lonora_db.trading_mode import set_trading_mode, trading_mode
from lonora_trading.controls import save_controls
from lonora_trading.execution import ExecutionService


async def checks() -> None:
    db = database()
    broker = ScriptedBroker()
    manager = cast(BrokerManager, ScriptedManager(broker))
    service = ExecutionService(db, manager)
    async with db.sessions() as session, session.begin():
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
    await save_controls(db, TradingControl(enabled=True))
    broker.account_id = account_id
    broker.scripted_positions = [
        Position(
            id="mode-position",
            symbol="FIXTURE",
            side="buy",
            volume=Decimal("0.2"),
            open_price=Decimal("10"),
        )
    ]

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
    result = await service.execute(owner_id, partial, lease)
    assert result.status == "confirmed" and broker.sent == 1, result

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
    assert result.details.get("send_state") == "not_sent" and broker.sent == 2

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
    print("trading mode checks passed")


if __name__ == "__main__":
    asyncio.run(checks())
