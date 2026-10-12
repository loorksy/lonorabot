from typing import Any

from lonora_contracts.domain import Contract
from lonora_contracts.routines import RoutineCreate
from lonora_db.routines import create_routine, owned_routine, routine_data
from lonora_db.runs import require_lease
from lonora_db.schema import RoutineRow
from sqlalchemy import select

from .base import Tool
from .context import ToolContext
from .memory import Empty


class RoutineToggle(Contract):
    routine_id: str
    enabled: bool


async def create(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease, lock=True)
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
        await require_lease(session, context.lease, lock=True)
        row = await owned_routine(session, context.owner_id, args["routine_id"])
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
        Tool("routine_toggle", "Pause or resume a routine.", RoutineToggle, toggle),
    ]
