"""«سجل الإجراءات» (Q45): the owner-visible actions projected from durable events."""

from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from lonora_auth.identity import OwnerIdentity
from lonora_db.activity import activity

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/activity")


@router.get("")
async def read_activity(
    request: Request,
    limit: int = Query(default=50, ge=1, le=100),
    before: int | None = Query(default=None, ge=1),
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session:
        return await activity(session, owner.id, limit=limit, before=before)
