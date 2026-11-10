from datetime import timedelta
from typing import Any, Literal
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import Response
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import utcnow
from lonora_contracts.usage import UsagePeriod, UsageRank, UsageSeries
from lonora_core.user_error import LonoraError
from lonora_db.schema import UsageRow
from lonora_db.usage import (
    agent_usage,
    owner_zone,
    series_csv,
    usage_days,
    usage_rank,
    usage_series,
)
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


def valid_zone(tz: str | None) -> str | None:
    """An IANA zone name the server knows, or ``None`` for the owner's stored zone."""
    if tz is None:
        return None
    try:
        ZoneInfo(tz)
    except (ZoneInfoNotFoundError, ValueError, OSError):
        raise LonoraError("invalid_timezone", 422) from None
    return tz


Period = Query(default="month")
Tz = Query(default=None, max_length=64)
AgentFilter = Query(default=None, max_length=36)


@router.get("/agents")
async def agents(
    request: Request,
    days: int = Query(default=30, ge=1, le=366),
    agent_id: str | None = AgentFilter,
    bucket: Literal["day"] | None = Query(default=None),
    tz: str | None = Tz,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    """Model usage per agent over the last ``days`` (owner decision D4: a view, no cap).

    With ``bucket=day`` the period is the last ``days`` local days (today so far
    included) and ``buckets`` holds one entry per day for the selected agent(s)."""
    zone = valid_zone(tz)
    now = utcnow()
    async with runtime(request).db.sessions() as session:
        if bucket is None:
            since = now - timedelta(days=days)
            return {
                "days": days,
                "since": since.isoformat(),
                "agents": await agent_usage(session, owner.id, since, agent_id),
            }
        local = await owner_zone(session, owner.id, zone)
        since, buckets = await usage_days(session, owner.id, days, local, now, agent_id)
        return {
            "days": days,
            "since": since.isoformat(),
            "bucket": "day",
            "timezone": local.key,
            "agents": await agent_usage(session, owner.id, since, agent_id),
            "buckets": [item.model_dump(mode="json") for item in buckets],
        }


@router.get("/series", response_model=UsageSeries)
async def series(
    request: Request,
    period: UsagePeriod = Period,
    agent_id: str | None = AgentFilter,
    tz: str | None = Tz,
    owner: OwnerIdentity = Depends(require_owner),
) -> UsageSeries:
    """Cost and tokens per hour of today or per day, against the previous equal window,
    with the month to date and its projection (Q22: never a cap)."""
    zone = valid_zone(tz)
    async with runtime(request).db.sessions() as session:
        local = await owner_zone(session, owner.id, zone)
        return await usage_series(session, owner.id, period, local, utcnow(), agent_id)


@router.get("/rank", response_model=UsageRank)
async def rank(
    request: Request,
    period: UsagePeriod = Period,
    agent_id: str | None = AgentFilter,
    tz: str | None = Tz,
    owner: OwnerIdentity = Depends(require_owner),
) -> UsageRank:
    """The period's usage per agent and per model, most costly first."""
    zone = valid_zone(tz)
    async with runtime(request).db.sessions() as session:
        local = await owner_zone(session, owner.id, zone)
        return await usage_rank(session, owner.id, period, local, utcnow(), agent_id)


@router.get("/export.csv")
async def export_csv(
    request: Request,
    period: UsagePeriod = Period,
    agent_id: str | None = AgentFilter,
    tz: str | None = Tz,
    owner: OwnerIdentity = Depends(require_owner),
) -> Response:
    """The series' points as CSV (UTF-8 with BOM), the same numbers as ``/usage/series``."""
    zone = valid_zone(tz)
    now = utcnow()
    async with runtime(request).db.sessions() as session:
        local = await owner_zone(session, owner.id, zone)
        data = await usage_series(session, owner.id, period, local, now, agent_id)
    day = now.astimezone(local).date().isoformat()
    return Response(
        content=series_csv(data).encode("utf-8"),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="lonora-usage-{day}.csv"'},
    )
