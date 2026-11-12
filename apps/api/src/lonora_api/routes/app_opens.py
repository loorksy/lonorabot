"""The owner opened the app: the first open of each local date is kept (VISION 11.1)."""

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.app_opens import AppOpen
from lonora_contracts.domain import utcnow
from lonora_db.app_opens import record_open

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/app-opens")


@router.post("")
async def opened(
    request: Request, body: AppOpen, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    async with runtime(request).db.sessions() as session, session.begin():
        recorded = await record_open(session, owner.id, body, utcnow())
    return {"recorded": recorded}
