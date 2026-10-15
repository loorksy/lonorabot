from typing import Any

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import RunRow, TradeApprovalRow
from .transactions import owned_thread


def approval_data(row: TradeApprovalRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "run_id": row.run_id,
        "thread_id": row.thread_id,
        "agent_id": row.agent_id,
        "timeline_seq": row.timeline_seq,
        "requests": row.requests,
        "status": row.status,
        "results": row.results,
        "created_at": row.created_at.isoformat(),
    }


def approval_event(session: AsyncSession, row: TradeApprovalRow) -> None:
    emit(
        session,
        row.owner_id,
        "trading.approval.updated",
        thread_id=row.thread_id,
        agent_id=row.agent_id,
        run_id=row.run_id,
        payload=approval_data(row),
    )


async def decide(
    session: AsyncSession, owner_id: str, approval_id: str, decision: str
) -> dict[str, Any]:
    candidate = await session.get(TradeApprovalRow, approval_id)
    if candidate is None or candidate.owner_id != owner_id:
        raise LonoraError("trade_approval_not_found", 404)
    await owned_thread(session, owner_id, candidate.thread_id, lock=True)
    run = await session.scalar(
        select(RunRow).where(RunRow.id == candidate.run_id).with_for_update()
    )
    row = await session.scalar(
        select(TradeApprovalRow).where(TradeApprovalRow.id == approval_id).with_for_update()
    )
    assert row is not None
    desired = "approved" if decision == "approve" else "rejected"
    if row.status != "pending":
        if row.status != desired and not (decision == "approve" and row.status == "completed"):
            raise LonoraError("trade_approval_already_decided", 409)
        return approval_data(row)
    if run is None or run.status not in {"waiting_input", "running", "leased", "queued"}:
        raise LonoraError("trade_approval_run_unavailable", 409)
    pending_calls = run.execution_state.get("pending", [])
    if run.execution_state and not any(call.get("id") == row.call_id for call in pending_calls):
        raise LonoraError("trade_approval_run_unavailable", 409)
    row.status, row.updated_at = desired, utcnow()
    if run.status == "waiting_input":
        run.status = "queued"
        run.updated_at = utcnow()
        emit(
            session,
            owner_id,
            "run.queued",
            thread_id=row.thread_id,
            agent_id=row.agent_id,
            run_id=run.id,
        )
    approval_event(session, row)
    return approval_data(row)
