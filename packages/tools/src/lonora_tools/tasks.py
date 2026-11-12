from typing import Any

from lonora_contracts.tasks import TaskControl, TaskCreate, TaskInspect, TaskStepUpdate, TaskWait
from lonora_core.user_error import LonoraError
from lonora_db.genui_taint import taint_row_from
from lonora_db.runs import require_lease
from lonora_db.schema import TicketRow
from lonora_db.tasks import control_task, create_task, get_task, snapshot
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .base import Tool, eager_for
from .context import ToolContext
from .provenance import owner_message_id
from .resolve import Option, resolve, stating


async def step_update(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_db.tasks import update_task_step

    async with context.db.sessions() as session, session.begin():
        return await snapshot(
            session,
            await update_task_step(session, context.lease, TaskStepUpdate.model_validate(args)),
        )


async def start(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease)
        row = await create_task(
            session,
            context.owner_id,
            context.agent_id,
            context.thread_id,
            TaskCreate.model_validate(args),
            context.resource_id,
            starter=run,
        )
        return await snapshot(session, row)


async def named_task(
    session: AsyncSession, context: ToolContext, requested: str
) -> tuple[str, dict[str, Any] | None]:
    """The task a read named by its id, or the agent's own task by its title."""
    found = await session.get(TicketRow, requested)
    if found is not None and found.owner_id == context.owner_id:
        return requested, None
    rows = await session.scalars(
        select(TicketRow)
        .where(TicketRow.owner_id == context.owner_id, TicketRow.agent_id == context.agent_id)
        .order_by(TicketRow.updated_at.desc())
        .limit(200)
    )
    options = [
        Option(
            row.id,
            (str(row.payload.get("title") or ""),),
            {"title": row.payload.get("title"), "status": row.state["task"].get("status")},
        )
        for row in rows
        if row.state.get("task")
    ]
    return resolve(
        requested,
        options,
        missing="task_not_found",
        argument="task_id",
        use="any",
        listing="task_inspect",
    )


async def inspect(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        named = None
        if args.get("task_id"):
            task_id, named = await named_task(session, context, args["task_id"])
            rows = [await get_task(session, context.owner_id, task_id)]
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
        tasks = [await snapshot(session, row) for row in rows if row.state.get("task")]
        return stating({"tasks": tasks}, named)


async def control(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease)
        row = await control_task(
            session,
            context.owner_id,
            TaskControl.model_validate(args),
            agent_id=context.agent_id,
            owner_message=await owner_message_id(session, run) is not None,
        )
        # Tainted work that resumes or revises a Task taints it (GENUI_PLAN §8.5).
        await taint_row_from(session, run, "ticket", row.id)
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
            eager=eager_for("task"),
        ),
        Tool(
            "task_step_update",
            "Update this background task's declared step using actual successful persisted tool-call IDs. Completed steps cannot be rewritten; do not invent percentages or evidence.",
            TaskStepUpdate,
            step_update,
            replay_safe=True,
            eager=eager_for("task"),
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
            poller=True,
        ),
        Tool(
            "task_control",
            "Apply a contextual task pause/resume/cancel/plan revision with optimistic version checking. Completed steps cannot be rewritten. Pause/cancel occurs at a safe tool boundary.",
            TaskControl,
            control,
            search_terms="delete remove cancel stop clear erase suspend حذف احذف امسح مسح ألغ ألغِ الغ إلغاء الغاء أوقف وقف ايقاف إيقاف شيل ازل أزل إزالة علق task tasks job jobs مهمة المهمة مهام المهام",
        ),
    ]
