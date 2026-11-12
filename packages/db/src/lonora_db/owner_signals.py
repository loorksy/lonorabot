"""The owner's behavior as the server saw it (8.1), and the one owner-model reader (8.3).

Signals are appended where they happen: a conversation read, a position closed
outside Lonora. They are facts with a time, never a judgment; Lonora reads a
small summary on its wake and writes what it concludes to the owner profile.
"""

from datetime import timedelta
from typing import Any
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from lonora_contracts.domain import utcnow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .owner_profile import owner_preferences, read_owner_profile
from .schema import AgentRow, OwnerSignalRow

SIGNAL_DAYS = 14
SIGNAL_CLOSES = 10


def record_signal(
    session: AsyncSession,
    owner_id: str,
    kind: str,
    *,
    thread_id: str | None = None,
    agent_id: str | None = None,
    details: dict[str, Any] | None = None,
) -> None:
    session.add(
        OwnerSignalRow(
            owner_id=owner_id,
            kind=kind,
            thread_id=thread_id,
            agent_id=agent_id,
            details=details or {},
            observed_at=utcnow(),
        )
    )


def _zone(name: str | None) -> ZoneInfo:
    try:
        return ZoneInfo(name or "UTC")
    except (ValueError, ZoneInfoNotFoundError, OSError):
        return ZoneInfo("UTC")


async def signal_summary(
    session: AsyncSession, owner_id: str, timezone: str | None
) -> dict[str, Any]:
    """The last two weeks in the owner's local time: when he read, what he closed."""
    zone = _zone(timezone)
    since = utcnow() - timedelta(days=SIGNAL_DAYS)
    rows = (
        await session.scalars(
            select(OwnerSignalRow)
            .where(OwnerSignalRow.owner_id == owner_id, OwnerSignalRow.observed_at >= since)
            .order_by(OwnerSignalRow.observed_at)
        )
    ).all()
    days: dict[str, dict[str, Any]] = {}
    closes: list[OwnerSignalRow] = []
    for row in rows:
        if row.kind == "external_close":
            closes.append(row)
            continue
        local = row.observed_at.astimezone(zone)
        day = days.setdefault(
            local.date().isoformat(), {"first_read": local.strftime("%H:%M"), "reads": 0}
        )
        day["last_read"] = local.strftime("%H:%M")
        day["reads"] += 1
    recent = closes[-SIGNAL_CLOSES:]
    names = {
        agent.id: agent.name
        for agent in (
            await session.scalars(
                select(AgentRow).where(
                    AgentRow.id.in_([row.agent_id for row in recent if row.agent_id])
                )
            )
        ).all()
    }
    return {
        "timezone": zone.key,
        "reads_by_day": [{"date": date, **day} for date, day in reversed(days.items())],
        "closes_outside_lonora": [
            {
                "at": row.observed_at.astimezone(zone).strftime("%Y-%m-%d %H:%M"),
                **row.details,
                "position_of": names.get(row.agent_id or "", "owner") if row.agent_id else "owner",
            }
            for row in reversed(recent)
        ],
    }


async def owner_model(session: AsyncSession, owner_id: str) -> dict[str, Any]:
    """Everything known about the owner, for any agent and for reports (8.3)."""
    row = await read_owner_profile(session, owner_id)
    preferences = await owner_preferences(session, owner_id)
    return {
        "profile": row.content if row else "",
        "profile_version": row.version if row else 1,
        "preferences": preferences,
        "signals": await signal_summary(session, owner_id, preferences["timezone"]),
    }
