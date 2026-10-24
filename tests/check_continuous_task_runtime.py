"""Task completion compatibility and recovery on disposable PostgreSQL only."""

import asyncio
from typing import Any, Literal

from check_streaming import Fixture
from lonora_agent.collaboration.outcome_return import return_outcome, return_pending_outcomes
from lonora_contracts.tasks import TaskControl, TaskCreate
from lonora_core.user_error import LonoraError
from lonora_db.runs import complete_run, fail_run, require_lease
from lonora_db.schema import MessageRow, RunRow
from lonora_db.tasks import checkpoint_task, control_task, create_task, get_task, task_state
from lonora_tools.context import ToolContext
from sqlalchemy import func, select


async def work(
    fixture: Fixture, mode: Literal["finite", "continuous"], title: str
) -> tuple[ToolContext, str, str]:
    agent = await fixture.agent(title)
    origin = await fixture.conversation(agent)
    async with fixture.runtime.db.sessions() as session, session.begin():
        task = await create_task(
            session,
            fixture.owner,
            agent["id"],
            origin["id"],
            TaskCreate(title=title, completion_mode=mode),
        )
        run = await session.get(RunRow, task.payload["run_id"])
        assert run
        data = {"id": run.id, "agent_id": run.agent_id, "thread_id": run.thread_id}
    return await fixture.lease(data), task.id, origin["id"]


async def rejected_completion(fixture: Fixture, context: ToolContext) -> None:
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            await complete_run(session, context.lease, "سأتابع الحساب.", {})
    except LonoraError as error:
        assert error.code == "task_wait_required", error.code
    else:
        raise AssertionError("a model text reply completed continuing responsibility")
    async with fixture.runtime.db.sessions() as session:
        row = await require_lease(session, context.lease)
        assert row.status == "running" and row.result is None


async def finite_compatibility(fixture: Fixture) -> None:
    context, identifier, origin = await work(fixture, "finite", "Finite independent review")
    async with fixture.runtime.db.sessions() as session, session.begin():
        assert await complete_run(session, context.lease, "راجعت الحالة الحالية.", {})
    await return_outcome(fixture.runtime.db, context.lease.run_id)
    await return_outcome(fixture.runtime.db, context.lease.run_id)
    async with fixture.runtime.db.sessions() as session:
        task = await get_task(session, fixture.owner, identifier)
        assert task_state(task).status == "completed"
        assert task_state(task).completion_mode == "finite"
        assert (
            await session.scalar(
                select(func.count())
                .select_from(MessageRow)
                .where(
                    MessageRow.thread_id == origin, MessageRow.content == "راجعت الحالة الحالية."
                )
            )
            == 1
        )
    print("PASS finite empty-plan Task still completes and returns one canonical result")


async def continuing_boundaries(fixture: Fixture) -> None:
    for legacy in (False, True):
        context, identifier, origin = await work(
            fixture, "continuous", "Legacy management" if legacy else "Continuing observation"
        )
        if legacy:
            async with fixture.runtime.db.sessions() as session, session.begin():
                task = await get_task(session, fixture.owner, identifier, lock=True)
                legacy_state: dict[str, Any] = dict(task.state["task"])
                legacy_state.pop("completion_mode")
                task.state = {**task.state, "task": legacy_state}
                run = await require_lease(session, context.lease, lock=True)
                # This old management marker restricts completion. It does not
                # authenticate trading authority or activate a financial grant.
                run.model_metadata = {**run.model_metadata, "account_management_id": "legacy"}
        await rejected_completion(fixture, context)
        async with fixture.runtime.db.sessions() as session:
            task = await get_task(session, fixture.owner, identifier)
            assert task_state(task).status == "queued"
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(MessageRow)
                    .where(MessageRow.thread_id == origin)
                )
                == 0
            )
        async with fixture.runtime.db.sessions() as session, session.begin():
            task = await get_task(session, fixture.owner, identifier)
            await control_task(
                session,
                fixture.owner,
                TaskControl(task_id=identifier, action="cancel", expected_version=task.version),
            )
        async with fixture.runtime.db.sessions() as session, session.begin():
            assert await checkpoint_task(session, context.lease)
        async with fixture.runtime.db.sessions() as session:
            task = await get_task(session, fixture.owner, identifier)
            row = await session.get(RunRow, context.lease.run_id)
            assert task_state(task).status == "cancelled"
            assert row and row.status == "cancelled"
    print("PASS continuous and legacy management cannot complete from prose; owner stop wins")


async def terminal_legacy_stays_terminal(fixture: Fixture) -> None:
    context, identifier, _ = await work(fixture, "continuous", "Old completed management")
    async with fixture.runtime.db.sessions() as session, session.begin():
        task = await get_task(session, fixture.owner, identifier, lock=True)
        old = dict(task.state["task"])
        old.pop("completion_mode")
        old.update(status="completed", phase="completed")
        task.state = {**task.state, "task": old}
        task.payload = {**task.payload, "status": "completed"}
        row = await require_lease(session, context.lease, lock=True)
        row.model_metadata = {**row.model_metadata, "account_management_id": "legacy"}
        row.status, row.lease_expires_at = "completed", None
    await return_pending_outcomes(fixture.runtime.db)
    await return_pending_outcomes(fixture.runtime.db)
    async with fixture.runtime.db.sessions() as session:
        task = await get_task(session, fixture.owner, identifier)
        row = await session.get(RunRow, context.lease.run_id)
        assert task_state(task).status == "completed"
        assert row and row.status == "completed"
        assert (
            await session.scalar(
                select(func.count()).select_from(RunRow).where(RunRow.thread_id == task.thread_id)
            )
            == 1
        )
    print("PASS historical completed management is preserved without automatic restart")


async def recover_continuing_work(fixture: Fixture) -> None:
    context, identifier, _ = await work(fixture, "continuous", "Revise ongoing review")
    async with fixture.runtime.db.sessions() as session, session.begin():
        await fail_run(session, context.lease, "task_wait_required")
    await return_outcome(fixture.runtime.db, context.lease.run_id)
    async with fixture.runtime.db.sessions() as session:
        task = await get_task(session, fixture.owner, identifier)
        state = task_state(task)
        assert state.status == "failed" and state.failure
        assert state.failure.recovery == "modify_plan"
    async with fixture.runtime.db.sessions() as session, session.begin():
        task = await get_task(session, fixture.owner, identifier)
        await control_task(
            session,
            fixture.owner,
            TaskControl(
                task_id=identifier,
                action="revise",
                expected_version=task.version,
                instruction="راجع بيانات السوق الحديثة ثم احفظ موعد المتابعة الفعلي.",
            ),
        )
    async with fixture.runtime.db.sessions() as session, session.begin():
        task = await get_task(session, fixture.owner, identifier)
        await control_task(
            session,
            fixture.owner,
            TaskControl(task_id=identifier, action="resume", expected_version=task.version),
        )
    async with fixture.runtime.db.sessions() as session:
        task = await get_task(session, fixture.owner, identifier)
        row = await session.get(RunRow, context.lease.run_id)
        assert task_state(task).completion_mode == "continuous"
        assert task_state(task).status == "queued" and task_state(task).attempt == 2
        assert row and row.id == task.payload["run_id"] and row.status == "queued"
    print("PASS missing real wait is recoverable by explicit plan revision on the same Task/Run")


async def main() -> None:
    fixture = await Fixture().open()
    try:
        await finite_compatibility(fixture)
        await continuing_boundaries(fixture)
        await terminal_legacy_stays_terminal(fixture)
        await recover_continuing_work(fixture)
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
