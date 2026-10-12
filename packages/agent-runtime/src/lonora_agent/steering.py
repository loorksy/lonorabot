from typing import Any

from lonora_adapter_kit.types import ModelMessage
from lonora_db.runs import checkpoint
from lonora_db.steering import consume_steering
from lonora_tools.context import ToolContext


async def merge_steering(
    context: ToolContext, state: dict[str, Any], messages: list[ModelMessage]
) -> bool:
    async with context.db.sessions() as session, session.begin():
        fresh = await consume_steering(session, context.lease)
        for row in fresh:
            messages.append(ModelMessage(role="user", content=row.content))
        if fresh:
            state["messages"] = [message.model_dump(mode="json") for message in messages]
            await checkpoint(session, context.lease, state)
        return bool(fresh)
