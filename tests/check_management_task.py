"""Full mode's continuous account-management task on PostgreSQL (mandate 4.5, 14.3.3).

Scripted broker only; no live orders. Run on a fresh disposable *_test database.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from check_trading import ScriptedBroker, ScriptedManager, database
from lonora_adapters.brokers.base import BrokerManager
from lonora_agent.collaboration.agent_create import delete_created_agent
from lonora_api.routes.owner_actions import undo_creation
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.account import Position
from lonora_contracts.agent_permissions import PermissionChange
from lonora_contracts.domain import AgentUpdate, utcnow
from lonora_contracts.runs import Lease
from lonora_contracts.tasks import TaskCreate, TaskFailure
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_core.user_error import LonoraError
from lonora_db.account_authority import revoke
from lonora_db.agent_creation import pause_agent
from lonora_db.agent_permissions import change_permission
from lonora_db.agents import update_agent
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.management_task import MARKER, live_management_task, open_management_tasks
from lonora_db.obligations import prepare_delete
from lonora_db.routines import due_query
from lonora_db.schema import (
    AccountAuthorityRow,
    AgentRow,
    MarketWatchRow,
    OwnerActionRow,
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
from lonora_trading.execution import ExecutionService, require_task_authority
from lonora_trading.idempotency import trade_fingerprint
from lonora_trading.manual_activity import material_state
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


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

    # 4.5.2: switching to Ask ends it. 4.5.3: watches and routines stay; the Run woken
    # by its timer goes on outside the task, under Ask.
    await tap("ask", by="agent")
    assert await live() is None
    async with db.sessions() as session:
        row = await session.get(TicketRow, task_id)
        kickoff = await session.get(RunRow, task.payload["run_id"])
        assert row is not None and kickoff is not None
        assert task_state(row).status == "cancelled"
        assert kickoff.status == "queued" and "task_id" not in kickoff.model_metadata
        kept = await session.get(MarketWatchRow, watch_id)
        assert kept is not None and kept.payload.get("enabled") is True
        assert "task_id" not in kept.state and kept.thread_id == conversation_id
        assert (await session.get(RoutineRow, routine_id)).enabled  # type: ignore[union-attr]
        # Outside the task, the Run passes the door's task check (6.9) like any Run.
        await require_task_authority(session, kickoff)
        kickoff_id = kickoff.id
    async with db.sessions() as session, session.begin():
        woken = await session.get(RunRow, kickoff_id)
        assert woken is not None
        woken.status = "completed"
    print("PASS Ask ends the task; its woken Run goes on outside it, watches and routines stay")

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

    async def started_task() -> tuple[TicketRow, str]:
        await tap("full")
        row = await live()
        assert row is not None
        return row, str(row.payload["run_id"])

    async def set_run(run_id: str, **changes: Any) -> None:
        async with db.sessions() as session, session.begin():
            run = await session.get(RunRow, run_id)
            assert run is not None
            for key, value in changes.items():
                setattr(run, key, value)

    # 4.5.3: ending never cancels the agent's own timer. The task's pending timer becomes
    # a one-shot routine in the agent's conversation at the same time.
    _, timer_run = await started_task()
    due = utcnow() + timedelta(hours=2)
    await set_run(
        timer_run,
        status="waiting_takeover",
        execution_state={
            "environment": {"wait": {"kind": "timer", "call_id": "t", "due_at": due.isoformat()}}
        },
    )
    await tap("ask", by="agent")
    async with db.sessions() as session:
        timers = list(
            await session.scalars(
                select(RoutineRow).where(
                    RoutineRow.agent_id == agent_id, RoutineRow.run_at.is_not(None)
                )
            )
        )
        assert len(timers) == 1 and timers[0].run_at == due and timers[0].enabled
        assert timers[0].thread_id == conversation_id
        ended = await session.get(RunRow, timer_run)
        assert ended is not None and ended.status == "cancelled"
    print("PASS ending the task keeps its pending timer as a wake in the conversation")

    # A pause ends the task; the Run waiting on the owner's card leaves it with the card
    # still decidable (10.3.1.3), held while the agent is paused; the timer is held too.
    paused_task, card_run = await started_task()
    await set_run(card_run, status="waiting_input", execution_state={"messages": [{"x": 1}]})
    async with db.sessions() as session, session.begin():
        card = TradeApprovalRow(
            id=str(uuid4()),
            owner_id=owner_id,
            run_id=card_run,
            thread_id=paused_task.thread_id,
            agent_id=agent_id,
            call_id="card-call",
            requests=[],
        )
        session.add(card)
        await session.flush()
        card_id = card.id
    async with db.sessions() as session, session.begin():
        await pause_agent(session, owner_id, agent_id)
    assert await live() is None
    async with db.sessions() as session:
        held_run = await session.get(RunRow, card_run)
        held_card = await session.get(TradeApprovalRow, card_id)
        assert held_run is not None and held_run.status == "waiting_input"
        assert "task_id" not in held_run.model_metadata
        assert held_card is not None and held_card.status == "pending"
        # Due routines of a paused agent are not enqueued.
        assert await session.scalar(due_query(due + timedelta(minutes=1)).limit(1)) is None
    async with db.sessions() as session, session.begin():
        await update_agent(session, owner_id, agent_id, AgentUpdate(paused=False))
    assert await live() is not None
    async with db.sessions() as session:
        assert (await session.get(TradeApprovalRow, card_id)).status == "pending"  # type: ignore[union-attr]
    async with db.sessions() as session, session.begin():
        await update_agent(session, owner_id, agent_id, AgentUpdate(paused=True))
    assert await live() is None
    async with db.sessions() as session, session.begin():
        await update_agent(session, owner_id, agent_id, AgentUpdate(paused=False))
    assert await live() is not None
    await set_run(card_run, status="completed")
    print("PASS a pause ends the task, keeps its card decidable; the owner's resume restarts it")

    # A failed task that can still be resumed is ended by Ask, and is the agent's one task
    # for a Full tap; one that failed for good is closed before a new one starts.
    retrying = await live()
    assert retrying is not None

    async def fail(task_row: TicketRow, retry: bool) -> None:
        async with db.sessions() as session, session.begin():
            row = await session.get(TicketRow, task_row.id)
            assert row is not None
            state = task_state(row)
            state.status, state.phase = "failed", "failed"
            state.failure = TaskFailure(
                run_id=str(row.payload["run_id"]),
                lease_fence=1,
                attempt=1,
                code="model_provider_unavailable",
                recovery="automatic" if retry else "terminal",
                next_retry_at=(utcnow() + timedelta(minutes=5)).isoformat() if retry else None,
            )
            save_task(session, row, state)
        await set_run(str(task_row.payload["run_id"]), status="failed")

    await fail(retrying, retry=True)
    await tap("full")
    async with db.sessions() as session:
        assert await live() is not None and (await live()).id == retrying.id  # type: ignore[union-attr]
        assert len(await open_management_tasks(session, owner_id, agent_id)) == 1
    await tap("ask", by="agent")
    async with db.sessions() as session:
        row = await session.get(TicketRow, retrying.id)
        assert row is not None and task_state(row).status == "cancelled"
        failure = task_state(row).failure
        assert failure is not None and failure.next_retry_at is None
    for_good, _ = await started_task()
    await fail(for_good, retry=False)
    await tap("full")
    replacement = await live()
    assert replacement is not None and replacement.id != for_good.id
    async with db.sessions() as session:
        assert len(await open_management_tasks(session, owner_id, agent_id)) == 1
    async with db.sessions() as session, session.begin():
        await pause_agent(session, owner_id, agent_id)
    async with db.sessions() as session, session.begin():
        await update_agent(session, owner_id, agent_id, AgentUpdate(paused=False))
    async with db.sessions() as session:
        assert len(await open_management_tasks(session, owner_id, agent_id)) == 1
    print("PASS failed tasks are ended by Ask and pause and never stand beside a new one")

    # A Run working when the task ends goes on outside it: an in-flight exit passes the
    # door's task check, and what it creates from now on is the agent's, not the task's.
    working = await live()
    assert working is not None
    await set_run(str(working.payload["run_id"]), status="running")
    await tap("ask", by="agent")
    async with db.sessions() as session:
        run = await session.get(RunRow, working.payload["run_id"])
        assert run is not None and run.status == "running"
        assert "task_id" not in run.model_metadata
        await require_task_authority(session, run)
    await set_run(str(working.payload["run_id"]), status="completed")
    print("PASS a working Run leaves the task and keeps its exits")

    # Lock order: the pause, the owner's Undo of a creation card and the owner's delete
    # wait for a tool transaction of the task's Run that holds the Run and then needs the
    # agent (an FK key share); none of them deadlocks with it.
    async def contended(name: str, action: Callable[[AsyncSession], Awaitable[object]]) -> None:
        locked = await live()
        assert locked is not None
        holding, release = asyncio.Event(), asyncio.Event()

        async def tool_transaction() -> None:
            async with db.sessions() as session, session.begin():
                await session.execute(
                    select(RunRow).where(RunRow.id == locked.payload["run_id"]).with_for_update()
                )
                holding.set()
                await release.wait()
                await session.execute(
                    select(AgentRow).where(AgentRow.id == agent_id).with_for_update(key_share=True)
                )

        async def act() -> None:
            async with db.sessions() as session, session.begin():
                await action(session)

        tool = asyncio.create_task(tool_transaction())
        await holding.wait()
        acting = asyncio.create_task(act())
        await asyncio.sleep(0.3)
        assert not acting.done(), name + " did not wait for the task's Run"
        release.set()
        await asyncio.wait_for(asyncio.gather(tool, acting), timeout=20)
        assert await live() is None, name

    async def resume() -> None:
        async with db.sessions() as session, session.begin():
            await update_agent(session, owner_id, agent_id, AgentUpdate(paused=False))
        assert await live() is not None

    owner_identity = OwnerIdentity(id=owner_id, email="", token_hash="")
    await started_task()
    await contended("the pause", lambda session: pause_agent(session, owner_id, agent_id))
    await resume()
    await contended(
        "the creation card's Undo",
        lambda session: undo_creation(
            session,
            owner_identity,
            OwnerActionRow(id=str(uuid4()), payload={"agent_id": agent_id}),
        ),
    )
    await resume()
    print("PASS a pause and the Undo take the task's Run before the agent row: no deadlock")

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
        await revoke(session, owner_id, grant_id)
    assert await live() is not None, "revoking the grant did not hand over to the mode task"
    async with db.sessions() as session:
        grant_task = await session.get(TicketRow, stable_id(grant_id, "account-management-task"))
        assert grant_task is not None and task_state(grant_task).status == "cancelled"
    print("PASS the grant's task drives while its grant is active; revoking hands over")

    # Deleting a broker connection revokes its grants and hands a Full agent over to its
    # own task; a deleted agent or conversation gets none.
    await tap("ask", by="agent")
    async with db.sessions() as session, session.begin():
        other = await BrokerSessionRepository().create(
            session,
            owner_id,
            {"provider": "simulation", "account_id": "deleted-fixture", "enabled": True},
        )
        other_id = other.id
        grant = AccountAuthorityRow(
            owner_id=owner_id,
            agent_id=agent_id,
            thread_id=conversation_id,
            account_id=other_id,
            status="active",
            envelope={},
            envelope_hash="0" * 64,
            activation_expires_at=utcnow() + timedelta(minutes=5),
        )
        session.add(grant)
        await session.flush()
        await create_task(
            session,
            owner_id,
            agent_id,
            conversation_id,
            TaskCreate(title="grant management", completion_mode="continuous"),
            task_id=stable_id(grant.id, "account-management-task"),
        )
    await tap("full")
    assert await live() is None
    async with db.sessions() as session, session.begin():
        await prepare_delete(session, owner_id, account_id=other_id)
    assert await live() is not None, "deleting the connection left the Full agent without a task"
    print("PASS deleting a connection hands a Full agent over to its own task")

    # Deleting the agent ends the task before the agent row goes, also while a tool
    # transaction of the task's Run holds it (the owner's delete route).
    ending = await live()
    assert ending is not None
    await contended(
        "the owner's delete", lambda session: delete_created_agent(session, owner_id, agent_id)
    )
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
