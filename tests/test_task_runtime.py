"""Task lifecycle exercises the actual database ledger and shared run admission."""

import os
from collections.abc import AsyncGenerator
from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
import pytest_asyncio
from lonora_adapter_kit.types import ModelMessage
from lonora_contracts.domain import MessageCreate, utcnow
from lonora_contracts.runs import Lease
from lonora_contracts.tasks import TaskControl, TaskCreate, TaskStep
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.messages import send_message
from lonora_db.runs import claim_next, require_lease
from lonora_db.schema import AgentRow, Base, OwnerRow, RunRow, ThreadRow
from lonora_db.tasks import checkpoint_task, control_task, create_task, get_task, snapshot
from sqlalchemy import text
from sqlalchemy.engine import make_url
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine


@pytest_asyncio.fixture
async def task_db() -> AsyncGenerator[tuple[Database, str, str, str]]:
    # Isolated sqlite covers state/real SQL contract; PostgreSQL lock fencing is
    # additionally exercised by the existing check_streaming integration suite.
    explicit = os.environ.get("LONORA_TASK_TEST_DATABASE_URL")
    schema = "task_" + uuid4().hex
    if explicit:
        url = make_url(explicit)
        if not url.drivername.startswith("postgresql") or not (url.database or "").endswith(
            "_test"
        ):
            pytest.fail("Task checks require an explicit disposable *_test PostgreSQL database")
        engine = create_async_engine(
            explicit, connect_args={"server_settings": {"search_path": schema}}
        )
        db = Database(engine, async_sessionmaker(engine, expire_on_commit=False))
        async with engine.begin() as connection:
            await connection.execute(text('CREATE SCHEMA "' + schema + '"'))
    else:
        db = Database.connect("sqlite+aiosqlite:///:memory:")
    async with db.engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    async with db.sessions() as session, session.begin():
        owner = OwnerRow(email="task@example.test", password_hash="fixture")
        session.add(owner)
        await session.flush()
        agent = AgentRow(owner_id=owner.id, name="Task fixture")
        session.add(agent)
        await session.flush()
        thread = ThreadRow(owner_id=owner.id, agent_id=agent.id)
        session.add(thread)
        await session.flush()
    yield db, owner.id, agent.id, thread.id
    if explicit:
        async with db.engine.begin() as connection:
            await connection.execute(text('DROP SCHEMA "' + schema + '" CASCADE'))
    await db.close()


@pytest.mark.asyncio
async def test_same_agent_work_does_not_block_conversation(
    task_db: tuple[Database, str, str, str],
) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        task = await create_task(
            session,
            owner,
            agent,
            thread,
            TaskCreate(title="Analyze", steps=[TaskStep(id="read", title="Read evidence")]),
        )
        work = await claim_next(session, "background", 60, "work")
        assert work and work.thread_id != thread and work.agent_id == agent
        assert work is not None
        work.status = "running"
        work_id = work.id
    async with db.sessions() as session, session.begin():
        sent = await send_message(session, owner, thread, MessageCreate(content="Where are we?"))
        foreground = await claim_next(session, "foreground", 60, "conversation")
        assert foreground and foreground.thread_id == thread
        assert foreground.id in sent["run_ids"]
        assert foreground.agent_id == agent
        active_work = await session.get(RunRow, work_id)
        assert active_work is not None and active_work.status == "running"
        state = await snapshot(session, await get_task(session, owner, task.id))
        assert state["status"] == "running"
        assert state["origin_thread_id"] == thread


@pytest.mark.asyncio
async def test_pause_resume_checkpoint_and_fence_recovery(
    task_db: tuple[Database, str, str, str],
) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        task = await create_task(session, owner, agent, thread, TaskCreate(title="Observe"))
        run = await claim_next(session, "first", 60, "work")
        assert run is not None
        run.status = "running"
        run.execution_state = {"rounds": 2, "pending": [{"id": "stable-operation"}]}
        lease = Lease(run_id=run.id, owner="first", fence=run.lease_fence)
    async with db.sessions() as session, session.begin():
        row = await get_task(session, owner, task.id)
        await control_task(
            session,
            owner,
            TaskControl(task_id=row.id, action="pause", expected_version=row.version),
            agent_id=agent,
        )
        running = await session.get(RunRow, lease.run_id)
        assert running is not None and running.status == "running"
    async with db.sessions() as session, session.begin():
        assert await checkpoint_task(session, lease)
        row = await get_task(session, owner, task.id)
        assert (await snapshot(session, row))["status"] == "paused"
        await control_task(
            session,
            owner,
            TaskControl(task_id=row.id, action="resume", expected_version=row.version),
        )
    async with db.sessions() as session, session.begin():
        recovered = await claim_next(session, "second", 60, "work")
        assert recovered is not None
        assert recovered.id == lease.run_id and recovered.lease_fence > lease.fence
        assert recovered.execution_state["pending"][0]["id"] == "stable-operation"
        with pytest.raises(LonoraError, match="stale_lease"):
            await require_lease(session, lease)
        recovered.lease_expires_at = utcnow() - timedelta(seconds=1)
    async with db.sessions() as session, session.begin():
        recovered = await claim_next(session, "third", 60, "work")
        assert recovered and recovered.execution_state["rounds"] == 2


@pytest.mark.asyncio
async def test_controls_validate_owner_version_and_history(
    task_db: tuple[Database, str, str, str],
) -> None:
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        task = await create_task(session, owner, agent, thread, TaskCreate(title="Work"))
        identifier, version = task.id, task.version
    async with db.sessions() as session, session.begin():
        with pytest.raises(LonoraError, match="task_not_found"):
            await get_task(session, "another-owner", identifier)
        with pytest.raises(LonoraError, match="task_agent_mismatch"):
            await control_task(
                session,
                owner,
                TaskControl(task_id=identifier, action="pause", expected_version=version),
                agent_id="another-agent",
            )
        with pytest.raises(LonoraError, match="version_conflict"):
            await control_task(
                session,
                owner,
                TaskControl(task_id=identifier, action="pause", expected_version=version + 1),
            )
        row = await control_task(
            session,
            owner,
            TaskControl(
                task_id=identifier,
                action="revise",
                expected_version=version,
                instruction="Use the current plan; omit the pending export",
            ),
        )
        assert row.state["task"]["plan_revision"] == 2
        row = await control_task(
            session,
            owner,
            TaskControl(task_id=identifier, action="cancel", expected_version=row.version),
        )
        assert (await snapshot(session, row))["status"] == "cancelled"
        with pytest.raises(LonoraError, match="task_terminal"):
            await control_task(
                session,
                owner,
                TaskControl(task_id=identifier, action="resume", expected_version=row.version),
            )


@pytest.mark.asyncio
async def test_semantic_tool_control_and_revision_resume(
    task_db: tuple[Database, str, str, str],
) -> None:
    """The model's structured tool request is authoritative input, not phrase routing."""
    from pathlib import Path

    from lonora_adapter_kit.types import ToolCall
    from lonora_agent.tasks import task_checkpoint
    from lonora_tools.context import ToolContext
    from lonora_tools.registry import ToolRegistry
    from lonora_tools.tasks import tools

    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        sent = await send_message(
            session,
            owner,
            thread,
            MessageCreate(content="اجمع الأدلة واستمر حتى أصل، وقد أغيّر النطاق لاحقًا"),
        )
        foreground = await claim_next(session, "conversation", 60, "conversation")
        assert foreground and foreground.id in sent["run_ids"]
        foreground.status = "running"
        lease = Lease(run_id=foreground.id, owner="conversation", fence=foreground.lease_fence)
    context = ToolContext(
        db,
        owner,
        agent,
        thread,
        lease,
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
        Path("/tmp"),
    )
    registry = ToolRegistry(tools())
    result = await registry.execute(
        ToolCall(
            id="start-logical-work",
            name="task_start",
            arguments={"title": "Inspect market evidence"},
        ),
        context,
    )
    identifier = result["id"]
    repeated = await registry.execute(
        ToolCall(
            id="start-logical-work",
            name="task_start",
            arguments={"title": "Inspect market evidence"},
        ),
        context,
    )
    assert repeated["id"] == identifier
    changed = await registry.execute(
        ToolCall(
            id="adjust-scope",
            name="task_control",
            arguments={
                "task_id": identifier,
                "action": "revise",
                "expected_version": result["version"],
                "instruction": "Keep source reading; omit report publication",
            },
        ),
        context,
    )
    assert changed["plan_revision"] == 2
    inspected = await registry.execute(
        ToolCall(id="read-state", name="task_inspect", arguments={"task_id": identifier}), context
    )
    assert inspected["tasks"][0]["status"] == "queued"
    async with db.sessions() as session, session.begin():
        work = await claim_next(session, "work", 60, "work")
        assert work is not None
        work.status = "running"
        work_lease = Lease(run_id=work.id, owner="work", fence=work.lease_fence)
    work_context = ToolContext(
        db,
        owner,
        agent,
        work.thread_id,
        work_lease,
        context.brokers,
        context.trading,
        context.secrets,
        context.router,
        Path("/tmp"),
    )
    state: dict[str, Any] = {}
    messages: list[ModelMessage] = []
    await task_checkpoint(work_context, state, messages)
    assert state["task_plan_revision"] == 2
    assert "omit report publication" in messages[0].content
    async with db.sessions() as session:
        work = await session.get(RunRow, work_lease.run_id)
        assert work is not None
        assert work.execution_state["task_plan_revision"] == 2
        assert work.execution_state["messages"][0]["role"] == "user"


@pytest.mark.asyncio
async def test_step_completion_requires_real_checkpoint_evidence(
    task_db: tuple[Database, str, str, str],
) -> None:
    import json

    from lonora_contracts.tasks import TaskStepUpdate
    from lonora_db.tasks import update_task_step

    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        task = await create_task(
            session,
            owner,
            agent,
            thread,
            TaskCreate(title="Verify evidence", steps=[TaskStep(id="read", title="Read state")]),
        )
        run = await claim_next(session, "proof-worker", 60, "work")
        assert run
        run.status = "running"
        lease = Lease(run_id=run.id, owner="proof-worker", fence=run.lease_fence)
        with pytest.raises(LonoraError, match="task_step_evidence_required"):
            await update_task_step(
                session, lease, TaskStepUpdate(step_id="read", plan_revision=1, state="completed")
            )
        with pytest.raises(LonoraError, match="task_step_evidence_invalid"):
            await update_task_step(
                session,
                lease,
                TaskStepUpdate(
                    step_id="read",
                    plan_revision=1,
                    state="completed",
                    evidence_call_ids=["invented"],
                ),
            )
        run.execution_state = {
            "messages": [
                {
                    "role": "assistant",
                    "tool_calls": [{"id": "actual-read", "name": "account_read"}],
                },
                {
                    "role": "tool",
                    "tool_call_id": "actual-read",
                    "content": json.dumps({"ok": True, "account": {"balance": "1000"}}),
                },
            ]
        }
        await update_task_step(
            session,
            lease,
            TaskStepUpdate(
                step_id="read",
                plan_revision=1,
                state="completed",
                evidence_call_ids=["actual-read"],
            ),
        )
        actual = await get_task(session, owner, task.id)
        assert actual.state["task"]["steps"][0]["state"] == "completed"
        assert actual.state["task"]["steps"][0]["evidence_call_ids"] == ["actual-read"]
        with pytest.raises(LonoraError, match="task_completed_step_immutable"):
            await update_task_step(
                session, lease, TaskStepUpdate(step_id="read", plan_revision=1, state="running")
            )


@pytest.mark.asyncio
async def test_bounded_retry_preserves_checkpoint_steps_and_fencing(
    task_db: tuple[Database, str, str, str],
):
    from lonora_contracts.tasks import TaskRetryPolicy
    from lonora_db.runs import fail_run, require_lease
    from lonora_db.task_recovery import retry_due_tasks
    from lonora_db.tasks import finish_task, save_task, task_state

    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        task = await create_task(
            session,
            owner,
            agent,
            thread,
            TaskCreate(
                title="Read with bounded retry",
                steps=[TaskStep(id="read", title="Read", side_effect="read_only")],
                retry_policy=TaskRetryPolicy(
                    mode="automatic", maximum_attempts=3, initial_delay_seconds=5
                ),
            ),
        )
    first_lease = None
    for attempt in range(1, 4):
        async with db.sessions() as session, session.begin():
            run = await claim_next(session, "reader", 60, "work")
            assert run is not None
            lease = Lease(run_id=run.id, owner="reader", fence=run.lease_fence)
            first_lease = first_lease or lease
            run.execution_state = {
                **run.execution_state,
                "messages": [
                    {
                        "role": "assistant",
                        "tool_calls": [{"id": "same-read", "name": "account_read"}],
                    }
                ],
                "rounds": 4,
            }
            checkpoint = dict(run.execution_state)
            await fail_run(
                session, lease, "model_provider_unavailable", read_only_names={"account_read"}
            )
            row = await get_task(session, owner, task.id)
            state = task_state(row)
            assert state.failure and state.failure.attempt == attempt
            assert state.failure.code == "model_provider_unavailable"
            finish_task(session, row, "failed")
            result = await snapshot(session, row)
            if attempt == 3:
                assert state.failure.recovery == "terminal" and result["status"] == "failed"
                assert not result["can_resume"] and state.failure.next_retry_at is None
            else:
                assert result["status"] == "waiting" and state.failure.recovery == "automatic"
                assert state.failure.next_retry_at is not None
        if attempt < 3:
            assert await retry_due_tasks(db) == 0
            async with db.sessions() as session, session.begin():
                row = await get_task(session, owner, task.id, lock=True)
                state = task_state(row)
                assert state.failure
                state.failure.next_retry_at = (utcnow() - timedelta(seconds=1)).isoformat()
                save_task(session, row, state)
            assert await retry_due_tasks(db) == 1
            assert await retry_due_tasks(db) == 0
            async with db.sessions() as session:
                restored = await session.get(RunRow, lease.run_id)
                assert restored and restored.execution_state["messages"] == checkpoint["messages"]
                assert restored.execution_state["rounds"] == 0
                assert restored.execution_state["prior_attempt_rounds"] == attempt * 4
                assert first_lease is not None
                with pytest.raises(LonoraError, match="stale_lease"):
                    await require_lease(session, first_lease)
    assert await retry_due_tasks(db) == 0


@pytest.mark.asyncio
async def test_retry_wait_pause_cancel_and_restart(task_db: tuple[Database, str, str, str]):
    from lonora_contracts.tasks import TaskRetryPolicy
    from lonora_db.runs import fail_run
    from lonora_db.task_recovery import retry_due_tasks

    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        task = await create_task(
            session,
            owner,
            agent,
            thread,
            TaskCreate(
                title="Read later",
                steps=[TaskStep(id="read", title="Read", side_effect="read_only")],
                retry_policy=TaskRetryPolicy(mode="automatic"),
            ),
        )
        run = await claim_next(session, "reader", 60, "work")
        assert run
        await fail_run(
            session,
            Lease(run_id=run.id, owner="reader", fence=run.lease_fence),
            "model_rate_limited",
        )
        row = await get_task(session, owner, task.id)
        paused = await control_task(
            session,
            owner,
            TaskControl(task_id=row.id, action="pause", expected_version=row.version),
        )
        assert (await snapshot(session, paused))["status"] == "paused"
    assert await retry_due_tasks(db) == 0
    async with db.sessions() as session, session.begin():
        row = await get_task(session, owner, task.id)
        resumed = await control_task(
            session,
            owner,
            TaskControl(task_id=row.id, action="resume", expected_version=row.version),
        )
        assert (await snapshot(session, resumed))["status"] == "queued"
        cancelled = await control_task(
            session,
            owner,
            TaskControl(task_id=row.id, action="cancel", expected_version=resumed.version),
        )
        assert (await snapshot(session, cancelled))["status"] == "cancelled"
    assert await retry_due_tasks(db) == 0


@pytest.mark.asyncio
async def test_unknown_external_mutation_cannot_be_retried_by_declared_read_only_step(
    task_db: tuple[Database, str, str, str],
):
    from lonora_contracts.tasks import TaskRetryPolicy
    from lonora_db.runs import fail_run
    from lonora_db.task_recovery import retry_due_tasks

    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        task = await create_task(
            session,
            owner,
            agent,
            thread,
            TaskCreate(
                title="Misclassified work",
                steps=[TaskStep(id="read", title="Read", side_effect="read_only")],
                retry_policy=TaskRetryPolicy(mode="automatic"),
            ),
        )
        run = await claim_next(session, "reader", 60, "work")
        assert run
        run.execution_state = {
            "messages": [
                {
                    "role": "assistant",
                    "tool_calls": [{"id": "external-write", "name": "unknown_external_write"}],
                }
            ]
        }
        await fail_run(
            session,
            Lease(run_id=run.id, owner="reader", fence=run.lease_fence),
            "model_provider_unavailable",
            read_only_names={"account_read"},
        )
        row = await get_task(session, owner, task.id)
        view = await snapshot(session, row)
        assert (
            view["failure"]["recovery"] == "reconcile"
            and view["failure"]["reconciliation"] == "external"
        )
        assert not view["can_resume"]
        with pytest.raises(LonoraError, match="task_reconciliation_required"):
            await control_task(
                session,
                owner,
                TaskControl(task_id=row.id, action="resume", expected_version=row.version),
            )
    assert await retry_due_tasks(db) == 0


@pytest.mark.asyncio
async def test_financial_ambiguity_blocks_owner_resume_until_journal_settles(
    task_db: tuple[Database, str, str, str],
):
    from lonora_db.runs import fail_run
    from lonora_db.schema import TradingJournalRow

    db, owner, agent, thread = task_db
    operation = str(uuid4())
    async with db.sessions() as session, session.begin():
        task = await create_task(session, owner, agent, thread, TaskCreate(title="Financial state"))
        run = await claim_next(session, "reader", 60, "work")
        assert run
        run.execution_state = {
            "messages": [
                {"role": "assistant", "tool_calls": [{"id": "trade", "name": "trade_execute"}]}
            ]
        }
        session.add(
            TradingJournalRow(
                operation_id=operation,
                owner_id=owner,
                account_id="demo-fixture",
                request_hash="fixture",
                request={},
                status="ambiguous",
                result={"details": {"lease": {"run_id": run.id}}},
            )
        )
        await session.flush()
        await fail_run(
            session,
            Lease(run_id=run.id, owner="reader", fence=run.lease_fence),
            "model_provider_unavailable",
        )
        row = await get_task(session, owner, task.id)
        assert not (await snapshot(session, row))["can_resume"]
        with pytest.raises(LonoraError, match="task_reconciliation_required"):
            await control_task(
                session,
                owner,
                TaskControl(task_id=row.id, action="resume", expected_version=row.version),
            )
    async with db.sessions() as session, session.begin():
        journal = await session.get(TradingJournalRow, operation)
        assert journal
        journal.status = "confirmed"
        row = await get_task(session, owner, task.id)
        await session.flush()
        assert (await snapshot(session, row))["can_resume"]
        await control_task(
            session,
            owner,
            TaskControl(task_id=row.id, action="resume", expected_version=row.version),
        )
        restored = await session.get(RunRow, run.id)
        assert (
            restored and restored.execution_state["messages"][0]["tool_calls"][0]["id"] == "trade"
        )
        assert journal.operation_id == operation and journal.status == "confirmed"


@pytest.mark.asyncio
async def test_plan_failure_requires_actual_revision_before_resume(
    task_db: tuple[Database, str, str, str],
):
    from lonora_db.runs import fail_run

    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        task = await create_task(session, owner, agent, thread, TaskCreate(title="Bounded plan"))
        run = await claim_next(session, "reader", 60, "work")
        assert run
        await fail_run(
            session, Lease(run_id=run.id, owner="reader", fence=run.lease_fence), "tool_round_limit"
        )
        row = await get_task(session, owner, task.id)
        assert (await snapshot(session, row))["failure"]["recovery"] == "modify_plan"
        with pytest.raises(LonoraError, match="task_cannot_resume"):
            await control_task(
                session,
                owner,
                TaskControl(task_id=row.id, action="resume", expected_version=row.version),
            )
        revised = await control_task(
            session,
            owner,
            TaskControl(
                task_id=row.id,
                action="revise",
                expected_version=row.version,
                instruction="Continue only the remaining evidence retrieval.",
            ),
        )
        assert revised.state["task"]["plan_revision"] == 2
        resumed = await control_task(
            session,
            owner,
            TaskControl(task_id=row.id, action="resume", expected_version=revised.version),
        )
        assert (await snapshot(session, resumed))["attempt"] == 2


@pytest.mark.asyncio
async def test_run_cannot_complete_declared_unverified_task_steps(
    task_db: tuple[Database, str, str, str],
):
    from lonora_db.runs import complete_run

    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        await create_task(
            session,
            owner,
            agent,
            thread,
            TaskCreate(title="Evidence required", steps=[TaskStep(id="verify", title="Verify")]),
        )
        run = await claim_next(session, "reader", 60, "work")
        assert run
        with pytest.raises(LonoraError, match="task_steps_incomplete"):
            await complete_run(
                session,
                Lease(run_id=run.id, owner="reader", fence=run.lease_fence),
                "Claimed done without evidence",
                {},
            )
        assert run.status != "completed"
