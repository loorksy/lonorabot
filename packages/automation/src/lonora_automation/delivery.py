from typing import Any

from lonora_db.client import Database
from lonora_db.runs import run_data
from lonora_db.schema import RunRow
from sqlalchemy import select


async def routine_history(db: Database, routine_id: str, owner_id: str) -> list[dict[str, Any]]:
    from lonora_db.routines import owned_routine

    async with db.sessions() as session:
        row = await owned_routine(session, owner_id, routine_id)
        runs = (
            await session.scalars(
                select(RunRow)
                # By routine, not by thread: a routine moved to a new work thread keeps
                # its earlier runs.
                .where(
                    RunRow.agent_id == row.agent_id,
                    RunRow.trigger == "routine",
                    RunRow.model_metadata["routine_id"].as_string() == row.id,
                )
                .order_by(RunRow.created_at.desc())
                .limit(100)
            )
        ).all()
        return [run_data(run) for run in runs]
