from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_db.cancellation import cancel_run
from lonora_db.runs import run_data

from ..middleware.auth import require_owner, runtime

router = APIRouter()


@router.post("/runs/{run_id}/cancel")
async def cancel(
    request: Request, run_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return run_data(await cancel_run(session, owner.id, run_id))
