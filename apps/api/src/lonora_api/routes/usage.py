from fastapi import Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_db.usage import UsageRepository

from ..middleware.auth import require_owner, runtime
from . import resource_router

router = resource_router("/usage", UsageRepository())


@router.get("/summary")
async def summary(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, int]:
    async with runtime(request).db.sessions() as session:
        rows = await UsageRepository().list(session, owner.id)
    return {
        key: sum(int(row.payload.get(key, 0)) for row in rows)
        for key in ["input_tokens", "output_tokens", "cached_tokens"]
    }
