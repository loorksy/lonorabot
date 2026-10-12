from typing import Any

from lonora_contracts.domain import Contract
from lonora_db.memory import memory_data, read_memory
from lonora_memory.commit import atomic_commit
from pydantic import Field

from .base import Tool
from .context import ToolContext


class Empty(Contract):
    """No arguments are needed: memory is bound to the current persistent agent."""


class MemoryWrite(Contract):
    content: str = Field(max_length=30000)
    version: int = Field(ge=1)


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        return memory_data(await read_memory(session, context.owner_id, context.agent_id))


async def write(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return await atomic_commit(
        context.db,
        context.owner_id,
        context.agent_id,
        args["content"],
        args["version"],
        lease=context.lease,
        effect_key=context.effect_key,
    )


def tools() -> list[Tool]:
    return [
        Tool("memory_read", "Read this agent's durable MEMORY.md and revision.", Empty, read, True),
        Tool(
            "memory_write",
            "Atomically update MEMORY.md using its current revision; conflicts require re-reading.",
            MemoryWrite,
            write,
        ),
    ]
