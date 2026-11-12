"""When the owner opens the app (VISION 11.1: the brief time is learned from it; 8.1)."""

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from lonora_contracts.app_opens import AppOpen
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as postgres_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AppOpenRow

# The brief time reads the last 14 recorded days (VISION 11.1, lead: 7 to 14).
RECORDED_DAYS = 14
# The owner's day starts at 04:00 on the device's clock: an open at 00:30 belongs to the
# day before, so a late session is not that day's first open (8.1 "when the owner wakes").
DAY_START_HOUR = 4


async def record_open(
    session: AsyncSession, owner_id: str, request: AppOpen, now: datetime
) -> bool:
    """Keep the first open of the owner's day on the device's clock (from 04:00); a later
    open that day is not new."""
    local = now.astimezone(ZoneInfo(request.timezone)) - timedelta(hours=DAY_START_HOUR)
    local_date = local.date().isoformat()
    dialect = session.get_bind().dialect.name
    insert = postgres_insert if dialect == "postgresql" else sqlite_insert
    result = await session.execute(
        insert(AppOpenRow)
        .values(owner_id=owner_id, local_date=local_date, opened_at=now, timezone=request.timezone)
        .on_conflict_do_nothing(index_elements=[AppOpenRow.owner_id, AppOpenRow.local_date])
    )
    return bool(getattr(result, "rowcount", 0))


async def recorded_opens(session: AsyncSession, owner_id: str) -> list[AppOpenRow]:
    """The last recorded days' first opens, oldest first (the last is the latest open)."""
    rows = await session.scalars(
        select(AppOpenRow)
        .where(AppOpenRow.owner_id == owner_id)
        .order_by(AppOpenRow.opened_at.desc())
        .limit(RECORDED_DAYS)
    )
    return list(reversed(list(rows)))
