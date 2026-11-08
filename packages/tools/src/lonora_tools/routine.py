from typing import Any

from lonora_contracts.domain import Contract
from lonora_contracts.routines import RoutineCreate
from lonora_core.user_error import LonoraError
from lonora_db.routines import create_routine, owned_routine, routine_data
from lonora_db.runs import locked_run_thread, require_lease
from lonora_db.schema import RoutineRow
from lonora_db.supervision import control_work, refuse_held, supervises
from sqlalchemy import select

from .base import Tool
from .context import ToolContext
from .memory import Empty
from .restrictions import owner_message_id


class RoutineToggle(Contract):
    routine_id: str
    enabled: bool


async def create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        await locked_run_thread(session, context.lease)
        row = await create_routine(
            session,
            context.owner_id,
            context.agent_id,
            RoutineCreate.model_validate(args),
            context.resource_id,
        )
        return routine_data(row)


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        rows = (
            await session.scalars(
                select(RoutineRow).where(
                    RoutineRow.owner_id == context.owner_id, RoutineRow.agent_id == context.agent_id
                )
            )
        ).all()
        return {"routines": [routine_data(row) for row in rows]}


async def toggle(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        run = await require_lease(session, context.lease, lock=True)
        row = await owned_routine(session, context.owner_id, args["routine_id"])
        if row.agent_id != context.agent_id:
            # A supervised agent's routine follows the supervision rules; any other
            # agent's routine reads as not found.
            if not await supervises(session, context.owner_id, context.agent_id, row.agent_id):
                raise LonoraError("routine_not_found", 404)
            await control_work(
                session,
                context.owner_id,
                actor_id=context.agent_id,
                agent_id=row.agent_id,
                kind="routine",
                target_id=row.id,
                action="resume" if args["enabled"] else "pause",
                owner_message_id=await owner_message_id(session, run),
                run_id=run.id,
            )
            return routine_data(row)
        if args["enabled"]:
            # A routine a supervisor paused stays paused until it (or the owner) resumes it.
            await refuse_held(session, context.owner_id, "routine", row.id, context.agent_id)
        row.enabled = args["enabled"]
        return routine_data(row)


def tools() -> list[Tool]:
    return [
        Tool(
            "routine_create",
            "Schedule this same agent with either a cron expression/timezone or an interval; work continues with the browser closed.",
            RoutineCreate,
            create,
        ),
        Tool("routine_list", "Read scheduled work for this agent.", Empty, read, True),
        Tool(
            "routine_toggle",
            "Pause or resume one of your own routines, or one of an agent you supervise.",
            RoutineToggle,
            toggle,
        ),
    ]
