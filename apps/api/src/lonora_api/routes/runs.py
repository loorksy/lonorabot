from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.runs import RunRequest
from lonora_core.user_error import LonoraError
from lonora_db.runs import create_run, run_data
from lonora_db.schema import RunRow, ThreadRow
from lonora_db.transactions import owned_thread
from lonora_session.continuation import continuation_state
from sqlalchemy import or_, select

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/runs")


@router.get("")
async def list_runs(
    request: Request, thread_id: str | None = None, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        query = (
            select(RunRow)
            .join(ThreadRow, ThreadRow.id == RunRow.thread_id)
            .where(ThreadRow.owner_id == owner.id)
        )
        if thread_id:
            query = query.where(
                or_(
                    RunRow.thread_id == thread_id,
                    RunRow.parent_run_id.in_(
                        select(RunRow.id).where(RunRow.thread_id == thread_id)
                    ),
                )
            )
        rows = (await session.scalars(query.order_by(RunRow.created_at.desc()).limit(100))).all()
        return [run_data(row) for row in rows]


@router.post("", status_code=202)
async def create(
    request: Request, body: RunRequest, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return run_data(await create_run(session, owner.id, body))


@router.get("/{run_id}")
async def read(
    request: Request, run_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session:
        row = await session.get(RunRow, run_id)
        if row is None:
            raise LonoraError("run_not_found", 404)
        await owned_thread(session, owner.id, row.thread_id)
        return run_data(row)


@router.post("/{run_id}/resume")
async def resume(
    request: Request, run_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        row = await session.get(RunRow, run_id, with_for_update=True)
        if row is None:
            raise LonoraError("run_not_found", 404)
        await owned_thread(session, owner.id, row.thread_id)
        row.status = continuation_state(row.status)
        return run_data(row)
