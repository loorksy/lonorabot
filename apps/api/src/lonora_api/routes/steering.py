from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import MessageCreate
from lonora_core.user_error import LonoraError
from lonora_db.messages import send_message
from lonora_db.schema import RunRow

from ..middleware.auth import require_owner, runtime

router = APIRouter()


@router.post("/runs/{run_id}/steer", status_code=202)
async def steer(
    request: Request,
    run_id: str,
    body: MessageCreate,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        row = await session.get(RunRow, run_id)
        if row is None or row.status not in {"queued", "leased", "running", "waiting_input"}:
            raise LonoraError("run_not_active", 409)
        return await send_message(session, owner.id, row.thread_id, body)
