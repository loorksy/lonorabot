"""The owner's "What is running" view (mandate 7.1.5): every workspace process with the
agent that started it; one tap stops one process, one tap stops all of them. The listing
and the stops pass through the Gateway, the only service that reaches the workspace."""

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import Contract
from lonora_core.user_error import LonoraError
from lonora_db.workspace_running import request_stop, running_view
from pydantic import Field

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/workspace/running")


class StopOne(Contract):
    pid: int = Field(ge=1)
    agent_id: str = Field(min_length=1, max_length=36)


@router.get("")
async def running(request: Request, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session:
        return await running_view(session, owner.id)


@router.post("/stop", status_code=202)
async def stop_one(request: Request, body: StopOne, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session, session.begin():
        try:
            stop_id = await request_stop(session, owner.id, body.pid, body.agent_id)
        except LookupError:
            raise LonoraError("agent_not_found", 404) from None
    return {"id": stop_id}


@router.post("/stop-all", status_code=202)
async def stop_all(request: Request, owner: OwnerIdentity = Depends(require_owner)):
    async with runtime(request).db.sessions() as session, session.begin():
        stop_id = await request_stop(session, owner.id)
    return {"id": stop_id}
