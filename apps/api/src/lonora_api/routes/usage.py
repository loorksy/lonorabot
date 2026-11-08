from datetime import timedelta
from typing import Any

from fastapi import APIRouter, Depends, Query, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import utcnow
from lonora_db.schema import UsageRow
from lonora_db.usage import agent_usage
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


@router.get("/agents")
async def agents(
    request: Request,
    days: int = Query(default=30, ge=1, le=366),
    agent_id: str | None = Query(default=None, max_length=36),
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    """Model usage per agent over the last ``days`` (owner decision D4: a view, no cap)."""
    since = utcnow() - timedelta(days=days)
    async with runtime(request).db.sessions() as session:
        return {
            "days": days,
            "since": since.isoformat(),
            "agents": await agent_usage(session, owner.id, since, agent_id),
        }
