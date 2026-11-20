from lonora_contracts.domain import utcnow
from lonora_core.run_state import TERMINAL
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import RunRow
from .streaming import settle_stream
from .transactions import owned_thread


async def cancel_run(
    session: AsyncSession, owner_id: str, run_id: str, *, by: str | None = None
) -> RunRow:
    """Cancel a Run: the owner's Stop, or Lonora's ``cancel_run`` (``by``: Lonora's agent
    id, recorded so no client tells the owner it stopped a reply it did not stop)."""
    row = await session.get(RunRow, run_id)
    if row is None:
        raise LonoraError("run_not_found", 404)
    thread = await owned_thread(session, owner_id, row.thread_id, lock=True)
    row = await session.get(RunRow, run_id, with_for_update=True, populate_existing=True)
    if row is None:
        raise LonoraError("run_not_found", 404)
    await cancel_locked(session, thread.owner_id, row, by=by)
    return row


async def cancel_locked(
    session: AsyncSession, owner_id: str, row: RunRow, *, by: str | None = None
) -> None:
    """Cancel a Run the caller holds locked, and its unfinished children: its stream ends,
    its lease is fenced off, clients are told (``run.cancelled``) and a card send it never
    started is marked so. An agent's cancel is recorded on the Run
    (``model_metadata.cancelled_by``) and in the event; none is the owner's own Stop."""
    if row.status not in TERMINAL:
        row.status = "cancelled"
        settle_stream(row, "cancelled")
        row.lease_fence += 1
        row.lease_expires_at = None
        row.updated_at = utcnow()
        if by is not None:
            row.model_metadata = {**row.model_metadata, "cancelled_by": by}
        emit(
            session,
            owner_id,
            "run.cancelled",
            thread_id=row.thread_id,
            agent_id=row.agent_id,
            run_id=row.id,
            payload={"cancelled_by": by} if by is not None else None,
        )
        from .genui_submit import settle_unstarted

        await settle_unstarted(session, row)
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
        settle_stream(child, "cancelled")
        child.lease_fence += 1
        child.lease_expires_at = None
