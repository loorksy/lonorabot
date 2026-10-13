from typing import Any

from lonora_contracts.domain import Contract
from lonora_db.agent_directory import agent_directory
from pydantic import Field

from .base import Tool
from .context import ToolContext


class ListAgentsInput(Contract):
    name: str | None = Field(default=None, min_length=1, max_length=80)


async def list_agents(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        agents = await agent_directory(
            session, context.owner_id, context.agent_id, args.get("name")
        )
    return {"agents": agents}


def tools() -> list[Tool]:
    return [
        Tool(
            "list_agents",
            "List all of the owner's agents/colleagues with exact routing IDs, names, "
            "paused status and your own identity. Omit name for the full directory. "
            "Use this instead of search_internal to discover colleagues.",
            ListAgentsInput,
            list_agents,
            True,
        )
    ]
