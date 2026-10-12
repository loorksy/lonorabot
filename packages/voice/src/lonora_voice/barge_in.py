from lonora_db.cancellation import cancel_run
from lonora_db.client import Database
from lonora_db.schema import RunRow
from sqlalchemy import select


async def barge_in(db: Database, owner_id: str, thread_id: str) -> list[str]:
    async with db.sessions() as session, session.begin():
        runs = list(
            (
                await session.scalars(
                    select(RunRow).where(
                        RunRow.thread_id == thread_id, RunRow.status.in_(["leased", "running"])
                    )
                )
            ).all()
        )
        for run in runs:
            await cancel_run(session, owner_id, run.id)
        return [run.id for run in runs]
