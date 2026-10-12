from typing import Any

from lonora_adapter_kit.types import ModelMessage
from lonora_db.runs import checkpoint, require_lease
from lonora_db.schema import MessageRow, SteeringRow
from lonora_db.steering import consume_steering
from lonora_tools.context import ToolContext
from sqlalchemy import select

from .context.attachments import attachment_context


async def owner_steering_pending(context: ToolContext) -> bool:
    async with context.db.sessions() as session:
        await require_lease(session, context.lease)
        return (
            await session.scalar(
                select(SteeringRow.id)
                .join(MessageRow, MessageRow.id == SteeringRow.message_id)
                .where(
                    SteeringRow.run_id == context.lease.run_id,
                    SteeringRow.consumed.is_(False),
                    MessageRow.role == "user",
                )
                .limit(1)
            )
        ) is not None


async def merge_steering(
    context: ToolContext, state: dict[str, Any], messages: list[ModelMessage]
) -> bool:
    async with context.db.sessions() as session, session.begin():
        fresh = await consume_steering(session, context.lease)
        for row in fresh:
            notes, images = (
                await attachment_context(
                    session, context.owner_id, context.thread_id, row.seq, context.artifact_root
                )
                if row.attachment_ids
                else ("", [])
            )
            messages.append(
                ModelMessage(
                    role="user",
                    content=row.content + ("\n\n" + notes if notes else ""),
                    images=images,
                )
            )
        if fresh:
            state["messages"] = [message.model_dump(mode="json") for message in messages]
            await checkpoint(session, context.lease, state)
        return bool(fresh)
