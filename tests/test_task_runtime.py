"""Task lifecycle exercises the actual database ledger and shared run admission."""

import os
from collections.abc import AsyncGenerator
from datetime import timedelta
from uuid import uuid4

import pytest
import pytest_asyncio
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
async def test_same_agent_work_does_not_block_conversation(task_db):
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
        work.status = "running"
        work_id = work.id
    async with db.sessions() as session, session.begin():
        sent = await send_message(session, owner, thread, MessageCreate(content="Where are we?"))
        foreground = await claim_next(session, "foreground", 60, "conversation")
        assert foreground and foreground.thread_id == thread
        assert foreground.id in sent["run_ids"]
        assert foreground.agent_id == agent
        assert (await session.get(RunRow, work_id)).status == "running"
        state = await snapshot(session, await get_task(session, owner, task.id))
        assert state["status"] == "running"
        assert state["origin_thread_id"] == thread


@pytest.mark.asyncio
async def test_pause_resume_checkpoint_and_fence_recovery(task_db):
    db, owner, agent, thread = task_db
    async with db.sessions() as session, session.begin():
        task = await create_task(session, owner, agent, thread, TaskCreate(title="Observe"))
        run = await claim_next(session, "first", 60, "work")
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
        assert (await session.get(RunRow, lease.run_id)).status == "running"
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
        assert recovered.id == lease.run_id and recovered.lease_fence > lease.fence
        assert recovered.execution_state["pending"][0]["id"] == "stable-operation"
        with pytest.raises(LonoraError, match="stale_lease"):
            await require_lease(session, lease)
        recovered.lease_expires_at = utcnow() - timedelta(seconds=1)
    async with db.sessions() as session, session.begin():
        recovered = await claim_next(session, "third", 60, "work")
        assert recovered and recovered.execution_state["rounds"] == 2


@pytest.mark.asyncio
async def test_controls_validate_owner_version_and_history(task_db):
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
async def test_semantic_tool_control_and_revision_resume(task_db):
    """The model's structured tool request is authoritative input, not phrase routing."""
    from pathlib import Path
    from typing import cast

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
        cast(object, None),
        cast(object, None),
        cast(object, None),
        cast(object, None),
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
    state, messages = {}, []
    await task_checkpoint(work_context, state, messages)
    assert state["task_plan_revision"] == 2
    assert "omit report publication" in messages[0].content
    async with db.sessions() as session:
        work = await session.get(RunRow, work_lease.run_id)
        assert work.execution_state["task_plan_revision"] == 2
        assert work.execution_state["messages"][0]["role"] == "user"
