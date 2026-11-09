from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.search import SearchCategory
from lonora_db.search import owner_search

from ..middleware.auth import require_owner, runtime

router = APIRouter()


@router.get("/search")
async def search(
    request: Request,
    q: str = Query(default="", max_length=200),
    category: SearchCategory | None = None,
    limit: int = Query(default=32, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    """The owner's unified search; an empty ``q`` is the recent feed. Owner-wide, never
    an agent's."""
    async with runtime(request).db.sessions() as session:
        return await owner_search(session, owner.id, q, category, limit, offset)
