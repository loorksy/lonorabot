"""Cooperative task boundaries; never interrupt an in-flight atomic tool."""

from typing import Any

from lonora_adapter_kit.types import ModelMessage
from lonora_db.runs import checkpoint, require_lease
from lonora_db.schema import TicketRow
from lonora_db.tasks import checkpoint_task, task_state
from lonora_tools.context import ToolContext


class TaskSuspended(Exception):
    """A validated durable control was committed at a safe boundary."""


async def task_checkpoint(
    context: ToolContext,
    state: dict[str, Any] | None = None,
    messages: list[ModelMessage] | None = None,
) -> None:
    async with context.db.sessions() as session, session.begin():
        suspended = await checkpoint_task(session, context.lease)
        if not suspended and state is not None and messages is not None:
            run = await require_lease(session, context.lease)
            task_id = run.model_metadata.get("task_id")
            row = await session.get(TicketRow, task_id) if task_id else None
            if row and row.state.get("task"):
                task = task_state(row)
                if task.plan_revision > int(state.get("task_plan_revision", 0)):
                    messages.append(
                        ModelMessage(
                            role="user",
                            content="<task_plan_revision>"
                            + task.model_dump_json(
                                include={"plan_revision", "steps", "instruction"}
                            )
                            + "</task_plan_revision>",
                        )
                    )
                    state["task_plan_revision"] = task.plan_revision
                    state["messages"] = [message.model_dump(mode="json") for message in messages]
                    await checkpoint(session, context.lease, state)
    if suspended:
        raise TaskSuspended()
