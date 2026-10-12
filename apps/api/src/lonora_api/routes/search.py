from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from lonora_auth.identity import OwnerIdentity
from lonora_tools.search import internal_search

from ..middleware.auth import require_owner, runtime

router = APIRouter()


@router.get("/search")
async def search(
    request: Request,
    q: str = Query(min_length=1, max_length=200),
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    return await internal_search(runtime(request).db, owner.id, q)
