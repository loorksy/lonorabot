"""Full mode's continuous account-management task on PostgreSQL (mandate 4.5, 14.3.3).

Scripted broker only; no live orders. Run on a fresh disposable *_test database.
"""

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from check_trading import ScriptedBroker, ScriptedManager, database
from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.account import Position
from lonora_contracts.agent_permissions import PermissionChange
from lonora_contracts.domain import AgentUpdate, utcnow
from lonora_contracts.runs import Lease
from lonora_contracts.tasks import TaskCreate
from lonora_contracts.trading import TradeRequest, TradeResult, TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import stop_management_task
from lonora_db.agent_creation import delete_agent, pause_agent
from lonora_db.agent_permissions import change_permission
from lonora_db.agents import update_agent
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.management_task import MARKER, live_management_task
from lonora_db.schema import (
    AccountAuthorityRow,
    AgentRow,
    MarketWatchRow,
    OwnerRow,
    RoutineRow,
    RunRow,
    ThreadRow,
    TicketRow,
    TradeApprovalRow,
)
from lonora_db.task_wait import resume_ready_waits
from lonora_db.tasks import (
    create_task,
    is_continuous_task,
    require_completed_task_steps,
    save_task,
    task_state,
)
from lonora_db.trading_journal import persist_result, reserve_operation
from lonora_db.trading_mode import set_trading_mode
from lonora_session.idempotency import stable_id
from lonora_trading.controls import save_controls
from lonora_trading.execution import ExecutionService
from lonora_trading.idempotency import trade_fingerprint
from lonora_trading.manual_activity import material_state
from sqlalchemy import func, select


async def mode_tasks(session: Any, agent_id: str) -> int:
    return int(
        await session.scalar(
            select(func.count())
            .select_from(TicketRow)
            .where(TicketRow.payload[MARKER].as_string() == agent_id)
        )
        or 0
    )


async def checks() -> None:
    db = database()
    broker = ScriptedBroker()
    manager = cast(BrokerManager, ScriptedManager(broker))
    service = ExecutionService(db, manager)
    async with db.sessions() as session, session.begin():
        owner = OwnerRow(email="management-task@example.test", password_hash="not-a-fixture-login")
        session.add(owner)
        await session.flush()
        owner_id = owner.id
        account = await BrokerSessionRepository().create(
            session,
            owner_id,
            {"provider": "simulation", "account_id": "management-task-fixture", "enabled": True},
        )
        account_id = account.id
        agent = AgentRow(owner_id=owner_id, name="Gold")
        session.add(agent)
        await session.flush()
        agent_id = agent.id
        conversation = ThreadRow(owner_id=owner_id, agent_id=agent_id)
        session.add(conversation)
        await session.flush()
        conversation_id = conversation.id
        chat = RunRow(
            thread_id=conversation_id,
            agent_id=agent_id,
            status="running",
            lease_owner="task-worker",
            lease_fence=1,
            lease_expires_at=utcnow() + timedelta(minutes=5),
        )
        session.add(chat)
        routine = RoutineRow(
            owner_id=owner_id,
            agent_id=agent_id,
            thread_id=conversation_id,
            prompt="Review the gold session open.",
            interval_seconds=3600,
            next_run_at=utcnow() + timedelta(hours=1),
        )
        session.add(routine)
        await session.flush()
        routine_id = routine.id
        lease = Lease(run_id=chat.id, owner="task-worker", fence=1)
        # The ladder keeps working until it is removed; this agent is at "Ask me".
        await change_permission(
            session, owner_id, agent_id, PermissionChange(level="supervised", expected_revision=0)
        )
    await save_controls(db, TradingControl(enabled=True))
    broker.account_id = account_id
    broker.scripted_positions = [
        Position(
            id="task-position",
            symbol="FIXTURE",
            side="buy",
            volume=Decimal("0.2"),
            open_price=Decimal("10"),
        )
    ]
    # The agent's own journaled order opened task-position.
    opening = TradeRequest(
        account_id=account_id,
        operation_id="task-open-" + uuid4().hex,
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
                broker_id="task-position",
                details={"position_id": "task-position"},
            ).model_dump(mode="json"),
        )

    async def tap(mode: str, by: str = "owner_tap") -> None:
        async with db.sessions() as session, session.begin():
            await set_trading_mode(session, owner_id, agent_id, mode, by=by)  # type: ignore[arg-type]

    async def live() -> TicketRow | None:
        async with db.sessions() as session, session.begin():
            return await live_management_task(session, owner_id, agent_id)

    # Ask has no management task.
    assert await live() is None

    # 4.5.1: the owner's tap on Full starts one continuous task, in the same transaction.
    await tap("full")
    task = await live()
    assert task is not None, "Full started no account-management task"
    task_id = task.id
    async with db.sessions() as session:
        assert await mode_tasks(session, agent_id) == 1
        state = task_state(task)
        assert state.completion_mode == "continuous" and state.status == "queued"
        assert state.origin_thread_id == conversation_id
        kickoff = await session.get(RunRow, task.payload["run_id"])
        assert kickoff is not None and kickoff.status == "queued"
        # Re-keyed per agent (14.3.3); bound to no account, so every connected account
        # is in it, an account connected later joins it and a disconnected one leaves it.
        assert kickoff.model_metadata["account_management_id"] == agent_id
        assert kickoff.model_metadata["task_id"] == task_id
        assert "account_id" not in kickoff.model_metadata
        assert is_continuous_task(state, kickoff)
    print("PASS Full starts one continuous account-management task keyed by the agent")

    # A second Full tap finds the running task and adds none.
    await tap("full")
    async with db.sessions() as session, session.begin():
        await BrokerSessionRepository().create(
            session,
            owner_id,
            {"provider": "simulation", "account_id": "second-fixture", "enabled": True},
        )
    again = await live()
    assert again is not None and again.id == task_id
    async with db.sessions() as session:
        assert await mode_tasks(session, agent_id) == 1
    print("PASS a second Full tap and a newly connected account keep the one task")

    # The kept continuous path: prose never completes it (task_wait_required).
    async with db.sessions() as session, session.begin():
        kickoff = await session.get(RunRow, task.payload["run_id"])
        assert kickoff is not None
        try:
            await require_completed_task_steps(session, kickoff)
            raise AssertionError("the continuous task could complete without a wait")
        except LonoraError as error:
            assert error.code == "task_wait_required"

    # A restart recovers it: the task waits on a timer; a new process resumes the same Run.
    async with db.sessions() as session, session.begin():
        row = await session.get(TicketRow, task_id)
        kickoff = await session.get(RunRow, task.payload["run_id"])
        assert row is not None and kickoff is not None
        state = task_state(row)
        state.status, state.phase, state.waiting_reason = "waiting", "waiting", "external_timer"
        save_task(session, row, state)
        kickoff.status = "waiting_takeover"
        kickoff.execution_state = {
            "environment": {
                "wait": {
                    "kind": "timer",
                    "source_id": None,
                    "task_id": task_id,
                    "run_id": kickoff.id,
                    "call_id": "timer-call",
                    "created_at": (utcnow() - timedelta(minutes=2)).isoformat(),
                    "due_at": (utcnow() - timedelta(minutes=1)).isoformat(),
                }
            }
        }
        # The task's own watch: the agent set it while working in the task.
        watch = MarketWatchRow(
            owner_id=owner_id,
            agent_id=agent_id,
            thread_id=row.thread_id,
            payload={"enabled": True, "symbol": "FIXTURE", "condition": "price_above"},
            state={"task_id": task_id, "task_run_id": kickoff.id},
        )
        session.add(watch)
        await session.flush()
        watch_id = watch.id
    restarted = database()
    assert await resume_ready_waits(restarted) >= 1
    async with restarted.sessions() as session:
        row = await session.get(TicketRow, task_id)
        kickoff = await session.get(RunRow, task.payload["run_id"])
        assert row is not None and kickoff is not None
        assert kickoff.status == "queued" and task_state(row).status == "queued"
        assert kickoff.model_metadata["account_management_id"] == agent_id
    print("PASS a restart resumes the same task Run through the kept recovery path")

    # 4.5.2: switching to Ask ends it. 4.5.3: watches and routines stay.
    await tap("ask", by="agent")
    assert await live() is None
    async with db.sessions() as session:
        row = await session.get(TicketRow, task_id)
        kickoff = await session.get(RunRow, task.payload["run_id"])
        assert row is not None and kickoff is not None
        assert task_state(row).status == "cancelled" and kickoff.status == "cancelled"
        kept = await session.get(MarketWatchRow, watch_id)
        assert kept is not None and kept.payload.get("enabled") is True
        assert "task_id" not in kept.state and kept.thread_id == conversation_id
        assert (await session.get(RoutineRow, routine_id)).enabled  # type: ignore[union-attr]
    print("PASS Ask ends the task; the agent's watch moves to its conversation, routines stay")

    # In Ask the agent still manages its own position: a partial close sends, no card.
    close = TradeRequest(
        account_id=account_id,
        operation_id="task-close-" + uuid4().hex,
        action="close_position",
        symbol="FIXTURE",
        position_id="task-position",
        volume=Decimal("0.1"),
    )
    result = await service.execute(
        owner_id, close, lease, expected_target=material_state(broker.scripted_positions[0])
    )
    assert result.status == "confirmed" and broker.sent == 1, result
    async with db.sessions() as session:
        cards = await session.scalar(
            select(func.count())
            .select_from(TradeApprovalRow)
            .where(TradeApprovalRow.agent_id == agent_id)
        )
        assert cards == 0
    print("PASS in Ask the agent closes its own position without a card")

    # Full again starts a new task; a pause ends it, the owner's resume starts it again.
    await tap("full")
    restarted_task = await live()
    assert restarted_task is not None and restarted_task.id != task_id
    async with db.sessions() as session, session.begin():
        await pause_agent(session, owner_id, agent_id)
    assert await live() is None
    async with db.sessions() as session, session.begin():
        await update_agent(session, owner_id, agent_id, AgentUpdate(paused=False))
    resumed = await live()
    assert resumed is not None
    async with db.sessions() as session, session.begin():
        await update_agent(session, owner_id, agent_id, AgentUpdate(paused=True))
    assert await live() is None
    async with db.sessions() as session, session.begin():
        await update_agent(session, owner_id, agent_id, AgentUpdate(paused=False))
    assert await live() is not None
    print("PASS a pause ends the task and the owner's resume of a Full agent starts it again")

    # An active signed grant's own Task drives the account until the grant is revoked.
    await tap("ask", by="agent")
    async with db.sessions() as session, session.begin():
        grant = AccountAuthorityRow(
            owner_id=owner_id,
            agent_id=agent_id,
            thread_id=conversation_id,
            account_id=account_id,
            status="active",
            envelope={},
            envelope_hash="0" * 64,
            activation_expires_at=utcnow() + timedelta(minutes=5),
        )
        session.add(grant)
        await session.flush()
        grant_id = grant.id
        await create_task(
            session,
            owner_id,
            agent_id,
            conversation_id,
            TaskCreate(title="grant management", completion_mode="continuous"),
            task_id=stable_id(grant_id, "account-management-task"),
        )
    await tap("full")
    assert await live() is None, "a Full-mode task ran beside the grant's own task"
    async with db.sessions() as session, session.begin():
        row = await session.get(AccountAuthorityRow, grant_id)
        assert row is not None
        row.status = "revoked"
        await stop_management_task(session, row)
    assert await live() is not None, "revoking the grant did not hand over to the mode task"
    async with db.sessions() as session:
        grant_task = await session.get(TicketRow, stable_id(grant_id, "account-management-task"))
        assert grant_task is not None and task_state(grant_task).status == "cancelled"
    print("PASS the grant's task drives while its grant is active; revoking hands over")

    # Deleting the agent ends the task before the agent row goes.
    ending = await live()
    assert ending is not None
    async with db.sessions() as session, session.begin():
        await delete_agent(session, owner_id, agent_id)
        with session.no_autoflush:
            row = await session.get(TicketRow, ending.id, populate_existing=True)
            assert row is not None and task_state(row).status == "cancelled"
    async with db.sessions() as session:
        assert await mode_tasks(session, agent_id) == 0
        queued = await session.scalar(
            select(func.count()).select_from(RunRow).where(RunRow.agent_id == agent_id)
        )
        assert queued == 0
    print("PASS deleting the agent ends its task")
    print("management task checks passed")


if __name__ == "__main__":
    asyncio.run(checks())
