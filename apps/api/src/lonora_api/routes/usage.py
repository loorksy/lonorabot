from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_db.schema import UsageRow
from sqlalchemy import func, select

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/usage")


@router.get("/summary")
async def summary(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, int]:
    async with runtime(request).db.sessions() as session:
        keys = ["input_tokens", "output_tokens", "cached_tokens"]
        query = select(
            *(
                func.coalesce(func.sum(UsageRow.payload[key].as_integer()), 0).label(key)
                for key in keys
            )
        ).where(UsageRow.owner_id == owner.id)
        totals = (await session.execute(query)).mappings().one()
        return {key: int(totals[key]) for key in keys}
