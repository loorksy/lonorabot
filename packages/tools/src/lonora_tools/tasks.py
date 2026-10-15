from typing import Any

from lonora_contracts.tasks import TaskControl, TaskCreate, TaskInspect
from lonora_core.user_error import LonoraError
from lonora_db.runs import require_lease
from lonora_db.schema import TicketRow
from lonora_db.tasks import control_task, create_task, get_task, snapshot
from sqlalchemy import select

from .base import Tool
from .context import ToolContext


async def start(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease)
        row = await create_task(
            session,
            context.owner_id,
            context.agent_id,
            context.thread_id,
            TaskCreate.model_validate(args),
            context.resource_id,
        )
        return await snapshot(session, row)


async def inspect(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        if args.get("task_id"):
            rows = [await get_task(session, context.owner_id, args["task_id"])]
        else:
            rows = list(
                await session.scalars(
                    select(TicketRow)
                    .where(
                        TicketRow.owner_id == context.owner_id,
                        TicketRow.agent_id == context.agent_id,
                    )
                    .order_by(TicketRow.updated_at.desc())
                    .limit(10)
                )
            )
        if any(row.agent_id != context.agent_id for row in rows):
            raise LonoraError("task_agent_mismatch", 403)
        return {"tasks": [await snapshot(session, row) for row in rows if row.state.get("task")]}


async def control(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease)
        row = await control_task(
            session, context.owner_id, TaskControl.model_validate(args), agent_id=context.agent_id
        )
        return await snapshot(session, row)


def tools() -> list[Tool]:
    return [
        Tool(
            "task_start",
            "Start durable background work as this same agent while the current conversation remains responsive. Use for substantial multi-step work; never report invented progress.",
            TaskCreate,
            start,
        ),
        Tool(
            "task_inspect",
            "Read actual durable task, checkpoint and run state before answering progress questions. Does not interrupt work.",
            TaskInspect,
            inspect,
            True,
        ),
        Tool(
            "task_control",
            "Apply a contextual task pause/resume/cancel/plan revision with optimistic version checking. Completed steps cannot be rewritten. Pause/cancel occurs at a safe tool boundary.",
            TaskControl,
            control,
        ),
    ]
