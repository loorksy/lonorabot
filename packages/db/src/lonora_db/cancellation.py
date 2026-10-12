from lonora_contracts.domain import utcnow
from lonora_core.run_state import TERMINAL
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import RunRow
from .transactions import owned_thread


async def cancel_run(session: AsyncSession, owner_id: str, run_id: str) -> RunRow:
    row = await session.get(RunRow, run_id, with_for_update=True)
    if row is None:
        raise LonoraError("run_not_found", 404)
    thread = await owned_thread(session, owner_id, row.thread_id, lock=True)
    if row.status not in TERMINAL:
        row.status = "cancelled"
        row.lease_fence += 1
        row.lease_expires_at = None
        row.updated_at = utcnow()
        emit(
            session,
            thread.owner_id,
            "run.cancelled",
            thread_id=row.thread_id,
            agent_id=row.agent_id,
            run_id=row.id,
        )
    children = list(
        (
            await session.scalars(
                select(RunRow)
                .where(RunRow.parent_run_id == row.id, RunRow.status.not_in(TERMINAL))
                .with_for_update()
            )
        ).all()
    )
    for child in children:
        child.status = "cancelled"
        child.lease_fence += 1
        child.lease_expires_at = None
    return row
