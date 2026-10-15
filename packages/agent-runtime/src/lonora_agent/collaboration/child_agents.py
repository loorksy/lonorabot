from typing import Any

from lonora_contracts.domain import AgentCreate
from lonora_core.user_error import LonoraError
from lonora_db.agents import agent_data, create_agent
from lonora_db.runs import require_lease
from lonora_db.schema import AgentRow
from lonora_tools.context import ToolContext


async def create_child(context: ToolContext, name: str, instructions: str) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
        existing = await session.get(AgentRow, context.resource_id)
        if existing:
            if existing.owner_id != context.owner_id or existing.parent_id != context.agent_id:
                raise LonoraError("child_agent_identity_conflict", 409)
            return agent_data(existing)
        row = await create_agent(
            session, context.owner_id, AgentCreate(name=name), context.agent_id, context.resource_id
        )
        row.instructions = instructions
        return agent_data(row)
