from typing import Any

from lonora_contracts.market_watch import Watch
from lonora_db.market_watches import MarketWatchRepository
from lonora_db.runs import require_lease
from lonora_db.transactions import resource_data

from .base import Tool
from .context import ToolContext
from .memory import Empty


async def create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease, lock=True)
        row = await session.get(MarketWatchRepository.row_type, context.resource_id)
        row = row or await MarketWatchRepository().create(
            session,
            context.owner_id,
            args,
            agent_id=context.agent_id,
            thread_id=context.thread_id,
            resource_id=context.resource_id,
        )
        if run.model_metadata.get("task_id"):
            row.state = {
                **row.state,
                "task_id": run.model_metadata["task_id"],
                "task_run_id": run.id,
            }
        return resource_data(row)


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        return {
            "watches": [
                resource_data(row)
                for row in await MarketWatchRepository().list(
                    session, context.owner_id, context.agent_id
                )
            ]
        }


def tools() -> list[Tool]:
    return [
        Tool(
            "watch_create",
            "Persist a server-side price, indicator, position, account, calendar or composite dynamic watch. A dynamic relationship detector compares this exact symbol with related_symbol on the same account, using closed-bar relationship_window evidence and relationship_states. It wakes this same agent for reassessment, never executes a trade directly.",
            Watch,
            create,
            replay_safe=True,
        ),
        Tool("watch_list", "Read this agent's durable market watches.", Empty, read, True),
    ]
