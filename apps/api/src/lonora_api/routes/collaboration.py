from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_db.collaboration import CollaborationRepository, current_session
from lonora_db.transactions import owned_thread, resource_data

from ..middleware.auth import require_owner, runtime

router = APIRouter()


@router.get("/threads/{thread_id}/collaboration")
async def current(
    request: Request, thread_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any] | None:
    async with runtime(request).db.sessions() as session:
        await owned_thread(session, owner.id, thread_id)
        row = await current_session(session, owner.id, thread_id)
        return resource_data(row) if row else None


@router.get("/collaboration/{session_id}")
async def inspect(
    request: Request, session_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session:
        return resource_data(await CollaborationRepository().get(session, owner.id, session_id))
