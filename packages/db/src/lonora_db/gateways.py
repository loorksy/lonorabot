"""Whether a Gateway is running, read from the heartbeat rows Gateways write
(``lonora_gateway.heartbeat``). Readiness and the watchdog count a heartbeat as fresh by
the same age; the stopped-worker item (Amendment 5) stands while none is."""

from datetime import UTC, datetime, timedelta

from lonora_contracts.domain import utcnow
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import GatewayRow

HEARTBEAT_FRESH = timedelta(seconds=45)


def aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=UTC)


def fresh(row: GatewayRow, now: datetime) -> bool:
    return row.state in {"running", "ready"} and now - aware(row.heartbeat_at) < HEARTBEAT_FRESH


async def gateway_running(session: AsyncSession, now: datetime | None = None) -> bool:
    moment = now or utcnow()
    return any(fresh(row, moment) for row in await session.scalars(select(GatewayRow)))


async def last_heartbeat(session: AsyncSession) -> datetime | None:
    value = await session.scalar(select(func.max(GatewayRow.heartbeat_at)))
    return aware(value) if value else None
