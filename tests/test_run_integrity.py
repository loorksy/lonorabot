"""Run integrity at the execution door (mandate 6.9, 14.3.4).

The door keeps the run lease, the run's Task authority, the refusal of research subagent
runs and of observe-only broker-activity wakes, and walks every ancestor run with the same
checks. A paused Task still lets risk-reducing requests through (4.7). Runs on the real
migrated PostgreSQL schema (skipped without ``LONORA_DATABASE_URL``).
"""

from decimal import Decimal
from typing import Any

import pytest
from lonora_contracts.runs import Lease
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from test_proactive_wakes import database

BUY = TradeRequest(account_id="acc", action="buy", symbol="XAUUSD", volume=Decimal("0.1"))


async def check(fixture: Any, lease: Lease, *, reducing: bool = False) -> str | None:
    """The door's run-integrity check for ``lease``: None, or the refusal code."""
    from lonora_trading.execution import require_goal_lineage

    async with fixture.runtime.db.sessions() as session:
        try:
            await require_goal_lineage(session, lease, None, fixture.owner, BUY, reducing=reducing)
        except LonoraError as error:
            return error.code
    return None


async def change_run(fixture: Any, run_id: str, **fields: Any) -> None:
    from lonora_db.schema import RunRow

    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(RunRow, run_id, with_for_update=True)
        assert row is not None
        for key, value in fields.items():
            setattr(row, key, value)


@pytest.mark.asyncio
async def test_the_door_keeps_lease_subagent_observe_only_and_ancestry_checks() -> None:
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Integrity")
        thread = await fixture.conversation(agent)
        parent = await fixture.lease(await fixture.run(agent, thread))
        child = await fixture.lease(await fixture.run(agent, thread))
        lease = child.lease
        assert await check(fixture, lease) is None
        # The lease: a stale fence is refused.
        assert await check(fixture, lease.model_copy(update={"fence": lease.fence + 1})) == (
            "stale_lease"
        )
        # A research subagent run and an observe-only wake never send.
        await change_run(fixture, lease.run_id, trigger="subagent")
        assert await check(fixture, lease) == "observe_only_execution_forbidden"
        await change_run(
            fixture, lease.run_id, trigger="user", model_metadata={"authority": "observe_only"}
        )
        assert await check(fixture, lease) == "observe_only_execution_forbidden"
        await change_run(fixture, lease.run_id, model_metadata={})
        # Every ancestor is checked the same way.
        await change_run(fixture, lease.run_id, parent_run_id=parent.lease.run_id)
        assert await check(fixture, lease) is None
        await change_run(fixture, parent.lease.run_id, model_metadata={"authority": "observe_only"})
        assert await check(fixture, lease) == "observe_only_execution_forbidden"
        await change_run(fixture, parent.lease.run_id, model_metadata={}, trigger="subagent")
        assert await check(fixture, lease) == "observe_only_execution_forbidden"
        # A cycle in the ancestry is refused.
        await change_run(fixture, parent.lease.run_id, trigger="user", parent_run_id=lease.run_id)
        assert await check(fixture, lease) == "goal_run_ancestry_invalid"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_task_authority_refuses_stopped_work_and_lets_a_paused_task_reduce_risk() -> None:
    database()
    from check_streaming import Fixture
    from lonora_contracts.tasks import TaskControl, TaskCreate
    from lonora_db.tasks import control_task, create_task, get_task

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Task integrity")
        thread = await fixture.conversation(agent)
        other = await fixture.conversation(await fixture.agent("Other"))
        context = await fixture.lease(await fixture.run(agent, thread))
        lease = context.lease
        async with fixture.runtime.db.sessions() as session, session.begin():
            task = await create_task(
                session, fixture.owner, agent["id"], thread["id"], TaskCreate(title="Manage")
            )
            task_id, task_thread = task.id, task.thread_id
        await change_run(
            fixture, lease.run_id, thread_id=task_thread, model_metadata={"task_id": task_id}
        )
        assert await check(fixture, lease) is None
        # A run must belong to its Task's agent and conversation.
        await change_run(fixture, lease.run_id, thread_id=other["id"])
        assert await check(fixture, lease) == "task_run_mismatch"
        await change_run(fixture, lease.run_id, thread_id=task_thread)
        # A paused Task sends no new risk, and still reduces its risk.
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await get_task(session, fixture.owner, task_id)
            await control_task(
                session,
                fixture.owner,
                TaskControl(task_id=task_id, action="pause", expected_version=row.version),
            )
        assert await check(fixture, lease) == "task_execution_stopped"
        assert await check(fixture, lease, reducing=True) is None
        # A cancelled Task sends nothing.
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await get_task(session, fixture.owner, task_id)
            await control_task(
                session,
                fixture.owner,
                TaskControl(task_id=task_id, action="cancel", expected_version=row.version),
            )
        assert await check(fixture, lease, reducing=True) == "task_execution_stopped"
        # Shadow runs never send.
        await change_run(fixture, lease.run_id, model_metadata={"execution_mode": "shadow"})
        assert await check(fixture, lease, reducing=True) == "shadow_execution_forbidden"
    finally:
        await fixture.close()
