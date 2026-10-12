from typing import Any

from lonora_contracts.domain import ScratchpadItem
from lonora_db.runs import require_lease
from lonora_db.scratchpad import ScratchpadRepository
from lonora_db.transactions import resource_data

from .base import Tool
from .context import ToolContext
from .memory import Empty


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        return {
            "items": [
                resource_data(row)
                for row in await ScratchpadRepository().list(
                    session, context.owner_id, context.agent_id
                )
            ]
        }


async def write(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        existing = await session.get(ScratchpadRepository.row_type, context.resource_id)
        row = existing or await ScratchpadRepository().create(
            session,
            context.owner_id,
            args,
            agent_id=context.agent_id,
            resource_id=context.resource_id,
        )
        return resource_data(row)


def tools() -> list[Tool]:
    return [
        Tool(
            "scratchpad_read",
            "Read this agent's operational notes, separate from long-term memory.",
            Empty,
            read,
            True,
        ),
        Tool("scratchpad_write", "Store a durable operational note.", ScratchpadItem, write),
    ]
