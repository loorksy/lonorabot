from typing import Any

from lonora_contracts.tasks import TaskControl, TaskCreate, TaskInspect, TaskStepUpdate, TaskWait
from lonora_core.user_error import LonoraError
from lonora_db.runs import require_lease
from lonora_db.schema import TicketRow
from lonora_db.tasks import control_task, create_task, get_task, snapshot
from sqlalchemy import select

from .base import Tool
from .context import ToolContext


async def step_update(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_db.tasks import update_task_step

    async with context.db.sessions() as session, session.begin():
        return await snapshot(
            session,
            await update_task_step(session, context.lease, TaskStepUpdate.model_validate(args)),
        )


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


async def wait(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_db.task_wait import prepare_wait

    async with context.db.sessions() as session, session.begin():
        source = await prepare_wait(
            session, context.lease, TaskWait.model_validate(args), context.call_id
        )
    return {"_runtime_external_wait": source, "task_id": source["task_id"], "status": "waiting"}


def tools() -> list[Tool]:
    return [
        Tool(
            "task_wait",
            "Suspend this same durable Task until its owned market watch triggers, its broker recovery is verified, or a timer is due. Continuous work must establish a real wait before yielding. Include a brief useful owner update in the accompanying assistant text when warranted; the server delivers it only after accepting this wait. No owner input or financial permission is implied. The same Run/checkpoint resumes and must revalidate external state.",
            TaskWait,
            wait,
            replay_safe=True,
        ),
        Tool(
            "task_step_update",
            "Update this background task's declared step using actual successful persisted tool-call IDs. Completed steps cannot be rewritten; do not invent percentages or evidence.",
            TaskStepUpdate,
            step_update,
            replay_safe=True,
        ),
        Tool(
            "task_start",
            "Start durable background work as this same agent while the current conversation remains responsive. Use finite completion for bounded results, continuous for ongoing monitoring or management until stopped. Neither mode grants trading authority; never report invented progress.",
            TaskCreate,
            start,
            replay_safe=True,
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
