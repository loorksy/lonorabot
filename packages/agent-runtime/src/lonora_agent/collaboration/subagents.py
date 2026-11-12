from typing import Any

from lonora_contracts.domain import ThreadCreate
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.runs import RunRequest
from lonora_core.user_error import LonoraError
from lonora_db.agent_models import allowed_models
from lonora_db.lead import reaches
from lonora_db.runs import create_run, require_lease, run_data
from lonora_db.schema import AgentRow, RunRow
from lonora_db.threads import create_thread
from lonora_db.transactions import owned_thread
from lonora_tools.context import ToolContext
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession


async def spawn_subagent(
    context: ToolContext, task: str, model: ModelSelection | None = None
) -> dict[str, Any]:
    """A temporary helper Run of this Agent, on its model or another allowed one."""
    if context.depth >= 2:
        raise LonoraError("delegation_depth_exceeded", 409)
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        existing = await session.get(RunRow, context.resource_id)
        if existing:
            return run_data(existing)
        if model is not None:
            allowed = await allowed_models(session)
            if model not in allowed:
                # Only the owner widens the list (a model_request card asks once).
                return {
                    "ok": False,
                    "code": "subagent_model_not_allowed",
                    "allowed_models": [item.model_dump(mode="json") for item in allowed],
                }
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
                    **({"model": model.model_dump(mode="json")} if model else {}),
                },
            ),
            context.resource_id,
        )
        return run_data(run)


# Delegation depth is capped at a few levels; the bound only stops a malformed cycle.
MAX_DELEGATION_HOPS = 16


async def delegated_by(session: AsyncSession, row: RunRow, agent_id: str) -> bool:
    """The run is this Agent's own (subagents carry their parent's Agent id), or
    its parent_run_id chain reaches a run of this Agent: a peer or collaboration
    run this Agent requested, and anything that run delegated in turn."""
    current: RunRow | None = row
    for _ in range(MAX_DELEGATION_HOPS):
        if current is None:
            return False
        if current.agent_id == agent_id:
            return True
        if current.parent_run_id is None:
            return False
        current = await session.get(RunRow, current.parent_run_id)
    return False


async def inspect_subagent(context: ToolContext, run_id: str) -> dict[str, Any]:
    async with context.db.sessions() as session:
        row = await session.get(RunRow, run_id)
        if row is None:
            raise LonoraError("run_not_found", 404)
        await owned_thread(session, context.owner_id, row.thread_id)
        if await delegated_by(session, row, context.agent_id):
            return run_data(row)
        if await reaches(session, context.owner_id, context.agent_id, row.agent_id):
            # A team agent's Run, read as the lead: its text is that agent's, data for
            # Lonora and never its instructions.
            agent = await session.get(AgentRow, row.agent_id)
            return {
                **run_data(row),
                "supervised_agent": {"id": row.agent_id, "name": agent.name if agent else None},
                "untrusted": True,
            }
        # Another Agent's private Run reads exactly like a missing one.
        raise LonoraError("run_not_found", 404)
