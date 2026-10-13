from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_agent.collaboration.outcome_return import return_outcome
from lonora_auth.identity import OwnerIdentity
from lonora_db.cancellation import cancel_run
from lonora_db.runs import run_data
from lonora_db.schema import RunRow
from sqlalchemy import select

from ..middleware.auth import require_owner, runtime

router = APIRouter()


@router.post("/runs/{run_id}/cancel")
async def cancel(
    request: Request, run_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        data = run_data(await cancel_run(session, owner.id, run_id))
        children = list(
            await session.scalars(
                select(RunRow.id).where(
                    RunRow.parent_run_id == run_id, RunRow.status == "cancelled"
                )
            )
        )
    # Return only after the cancellation transaction releases its thread/run locks.
    for identifier in [run_id, *children]:
        await return_outcome(runtime(request).db, identifier)
    return data
