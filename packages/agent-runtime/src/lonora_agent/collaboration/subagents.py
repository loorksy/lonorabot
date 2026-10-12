from typing import Any

from lonora_contracts.domain import ThreadCreate
from lonora_contracts.runs import RunRequest
from lonora_core.user_error import LonoraError
from lonora_db.runs import create_run, require_lease, run_data
from lonora_db.schema import RunRow
from lonora_db.threads import create_thread
from lonora_db.transactions import owned_thread
from lonora_tools.context import ToolContext
from sqlalchemy import func, select


async def spawn_subagent(context: ToolContext, task: str) -> dict[str, Any]:
    if context.depth >= 2:
        raise LonoraError("delegation_depth_exceeded", 409)
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        existing = await session.get(RunRow, context.resource_id)
        if existing:
            return run_data(existing)
        count = await session.scalar(
            select(func.count())
            .select_from(RunRow)
            .where(
                RunRow.parent_run_id == context.lease.run_id,
                RunRow.status.in_(["queued", "leased", "running", "waiting_input"]),
            )
        )
        if (count or 0) >= context.maximum_subagents:
            raise LonoraError("subagent_limit", 409)
        thread = await create_thread(
            session, context.owner_id, ThreadCreate(agent_id=context.agent_id, title=task[:80])
        )
        run = await create_run(
            session,
            context.owner_id,
            RunRequest(
                thread_id=thread.id,
                agent_id=context.agent_id,
                trigger="subagent",
                prompt=task,
                parent_run_id=context.lease.run_id,
                metadata={
                    "depth": context.depth + 1,
                    "return_thread_id": context.thread_id,
                    "return_agent_id": context.agent_id,
                },
            ),
            context.resource_id,
        )
        return run_data(run)


async def inspect_subagent(context: ToolContext, run_id: str) -> dict[str, Any]:
    async with context.db.sessions() as session:
        row = await session.get(RunRow, run_id)
        if row is None:
            raise LonoraError("run_not_found", 404)
        await owned_thread(session, context.owner_id, row.thread_id)
        return run_data(row)
