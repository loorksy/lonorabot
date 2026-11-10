import calendar
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Any, cast
from zoneinfo import ZoneInfo

from lonora_contracts.usage import (
    UsageDay,
    UsageFigures,
    UsageMonth,
    UsagePeriod,
    UsagePoint,
    UsagePreviousWindow,
    UsageRank,
    UsageRankAgent,
    UsageRankModel,
    UsageSeries,
    UsageWindow,
)
from lonora_core.model_pricing import PRICES_AS_OF, prompt_tokens, usage_cost
from pydantic import ValidationError
from sqlalchemy import RowMapping, func, literal_column, select
from sqlalchemy.ext.asyncio import AsyncSession

from .owner_profile import reach_me_policy
from .schema import AgentRow, UsageRow
from .transactions import ResourceRepository

TOKEN_KEYS = ("input_tokens", "output_tokens", "cached_tokens")


class UsageRepository(ResourceRepository):
    """Transactional, owner-scoped persistence for usage."""

    row_type = UsageRow
    kind = "usage"


async def agent_usage(
    session: AsyncSession, owner_id: str, since: datetime, agent_id: str | None = None
) -> list[dict[str, Any]]:
    """Model usage per Agent since ``since``, from the recorded requests: tokens and
    requests in total and per model, largest first. A view, never a cap (owner D4)."""
    provider = UsageRow.payload["provider"].as_string()
    model = UsageRow.payload["model"].as_string()
    query = (
        select(
            UsageRow.agent_id,
            provider.label("provider"),
            model.label("model"),
            func.count().label("requests"),
            func.max(UsageRow.created_at).label("last_used_at"),
            *(
                func.coalesce(func.sum(UsageRow.payload[key].as_integer()), 0).label(key)
                for key in TOKEN_KEYS
            ),
        )
        .where(UsageRow.owner_id == owner_id, UsageRow.created_at >= since)
        .group_by(UsageRow.agent_id, provider, model)
    )
    if agent_id is not None:
        query = query.where(UsageRow.agent_id == agent_id)
    rows = (await session.execute(query)).mappings().all()
    names = {
        row.id: row.name
        for row in await session.scalars(select(AgentRow).where(AgentRow.owner_id == owner_id))
    }
    agents: dict[str | None, dict[str, Any]] = {}
    for row in rows:
        entry = agents.setdefault(
            row["agent_id"],
            {
                "agent_id": row["agent_id"],
                "agent_name": names.get(row["agent_id"]) if row["agent_id"] else None,
                "requests": 0,
                "last_used_at": None,
                **dict.fromkeys(TOKEN_KEYS, 0),
                "cost_usd": 0.0,
                "unpriced_requests": 0,
                "models": [],
            },
        )
        tokens = {key: int(row[key]) for key in TOKEN_KEYS}
        entry["requests"] += int(row["requests"])
        for key in TOKEN_KEYS:
            entry[key] += tokens[key]
        last = row["last_used_at"]
        if last is not None and (entry["last_used_at"] is None or last > entry["last_used_at"]):
            entry["last_used_at"] = last
        cost = usage_cost(
            row["provider"] or "",
            row["model"] or "",
            tokens["input_tokens"],
            tokens["output_tokens"],
            tokens["cached_tokens"],
        )
        if cost is None:
            entry["unpriced_requests"] += int(row["requests"])
        else:
            entry["cost_usd"] += cost
        entry["models"].append(
            {
                "provider": row["provider"],
                "model": row["model"],
                "requests": int(row["requests"]),
                **tokens,
                "cost_usd": None if cost is None else round(cost, 6),
            }
        )
    result = sorted(
        agents.values(),
        key=lambda item: (
            -(item["input_tokens"] + item["output_tokens"]),
            item["agent_name"] or "",
        ),
    )
    for item in result:
        models = cast(list[dict[str, Any]], item["models"])
        models.sort(key=lambda model: -(model["input_tokens"] + model["output_tokens"]))
        item["last_used_at"] = item["last_used_at"].isoformat() if item["last_used_at"] else None
        item["cost_usd"] = round(item["cost_usd"], 6)
    return result


# --- Dashboard series, ranking and day buckets (WP-I; D4/Q22: a view, never a cap) -----
#
# Usage stays a resource payload: PostgreSQL groups the rows by the owner's local hour
# (``date_trunc('hour', timezone(zone, created_at))``), agent, provider and model, and
# each group is priced here, since a price is linear in tokens per model. The
# ``ln_usage (owner_id, created_at)`` index (migration ``0052_usage_cost``) serves the
# window scans.

PERIOD_DAYS: dict[UsagePeriod, int] = {"day": 1, "week": 7, "month": 30}


@dataclass
class Tally:
    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    requests: int = 0
    unpriced_requests: int = 0

    def add(self, row: RowMapping) -> None:
        provider, model = row["provider"] or "", row["model"] or ""
        inp, out, cached = (int(row[key]) for key in TOKEN_KEYS)
        requests = int(row["requests"])
        cost = usage_cost(provider, model, inp, out, cached)
        if cost is None:
            self.unpriced_requests += requests
        else:
            self.cost_usd += cost
        self.input_tokens += prompt_tokens(provider, inp, cached)
        self.output_tokens += out
        self.cached_tokens += cached
        self.requests += requests

    def figures(self) -> dict[str, Any]:
        return {
            "cost_usd": round(self.cost_usd, 6),
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
            "cached_tokens": self.cached_tokens,
            "tokens": self.input_tokens + self.output_tokens,
            "requests": self.requests,
            "unpriced_requests": self.unpriced_requests,
        }


async def owner_zone(session: AsyncSession, owner_id: str, requested: str | None) -> ZoneInfo:
    """The requested zone (validated by the caller), else the owner's stored zone, else UTC."""
    if requested:
        return ZoneInfo(requested)
    try:
        return ZoneInfo((await reach_me_policy(session, owner_id)).timezone)
    except (ValidationError, ValueError, KeyError):
        return ZoneInfo("UTC")


def _midnight(day: date, zone: ZoneInfo) -> datetime:
    return datetime.combine(day, time(), tzinfo=zone)


async def usage_groups(
    session: AsyncSession,
    owner_id: str,
    start: datetime,
    end: datetime,
    zone: ZoneInfo | None,
    agent_id: str | None = None,
) -> Sequence[RowMapping]:
    """Requests in ``[start, end)`` per agent, provider and model; with ``zone``, also per
    local hour (``local_hour``, a naive wall-clock time in that zone)."""
    provider = UsageRow.payload["provider"].as_string().label("provider")
    model = UsageRow.payload["model"].as_string().label("model")
    columns: list[Any] = [UsageRow.agent_id, provider, model]
    groups: list[Any] = [UsageRow.agent_id, literal_column("provider"), literal_column("model")]
    if zone is not None:
        local = func.timezone(zone.key, UsageRow.created_at)
        columns.append(func.date_trunc("hour", local).label("local_hour"))
        # Grouped by the output name: a repeated bound zone would not match the select's.
        groups.append(literal_column("local_hour"))
    query = (
        select(
            *columns,
            func.count().label("requests"),
            *(
                func.coalesce(func.sum(UsageRow.payload[key].as_integer()), 0).label(key)
                for key in TOKEN_KEYS
            ),
        )
        .where(
            UsageRow.owner_id == owner_id,
            UsageRow.created_at >= start,
            UsageRow.created_at < end,
        )
        .group_by(*groups)
    )
    if agent_id is not None:
        query = query.where(UsageRow.agent_id == agent_id)
    return (await session.execute(query)).mappings().all()


@dataclass(frozen=True)
class Windows:
    zone: ZoneInfo
    now: datetime
    today: date
    start: datetime
    previous_start: datetime
    previous_end: datetime
    month_start: datetime


def windows(period: UsagePeriod, zone: ZoneInfo, now: datetime) -> Windows:
    """The current window (``days`` local days ending now), the preceding window of the
    same length cut at the same wall-clock time, and the local month so far."""
    days = PERIOD_DAYS[period]
    local = now.astimezone(zone)
    today = local.date()
    previous_end = datetime.combine(
        today - timedelta(days=days), local.time().replace(tzinfo=None), tzinfo=zone
    )
    return Windows(
        zone=zone,
        now=now,
        today=today,
        start=_midnight(today - timedelta(days=days - 1), zone),
        previous_start=_midnight(today - timedelta(days=2 * days - 1), zone),
        previous_end=previous_end,
        month_start=_midnight(today.replace(day=1), zone),
    )


def _naive(value: datetime) -> datetime:
    return value.replace(tzinfo=None)


async def usage_series(
    session: AsyncSession,
    owner_id: str,
    period: UsagePeriod,
    zone: ZoneInfo,
    now: datetime,
    agent_id: str | None = None,
) -> UsageSeries:
    """Cost and tokens per hour (``day``) or per local day (``week``, ``month``), the
    previous equal window and the month to date with its projection. No limit (D4)."""
    w = windows(period, zone, now)
    end = now + timedelta(microseconds=1)
    first = min(w.start, w.month_start)
    groups = await usage_groups(session, owner_id, first, end, zone, agent_id)
    hourly = period == "day"
    keys: list[Any] = (
        [datetime.combine(w.today, time(hour)) for hour in range(24)]
        if hourly
        else [w.today - timedelta(days=k) for k in range(PERIOD_DAYS[period] - 1, -1, -1)]
    )
    points: dict[Any, Tally] = {key: Tally() for key in keys}
    totals, month = Tally(), Tally()
    start, month_start = _naive(w.start), _naive(w.month_start)
    for row in groups:
        hour: datetime = row["local_hour"]
        if hour >= start:
            key = hour if hourly else hour.date()
            if key in points:
                points[key].add(row)
            totals.add(row)
        if hour >= month_start:
            month.add(row)
    previous = Tally()
    for row in await usage_groups(
        session, owner_id, w.previous_start, w.previous_end, None, agent_id
    ):
        previous.add(row)
    local_now = _naive(now.astimezone(zone))
    current_hour = local_now.replace(minute=0, second=0, microsecond=0)
    series_points: list[UsagePoint] = []
    for key in keys:
        if hourly:
            point_start = key.replace(tzinfo=zone)
            future = key > current_hour
        else:
            point_start = _midnight(key, zone)
            future = False
        if future:
            series_points.append(
                UsagePoint(
                    start=point_start,
                    cost_usd=None,
                    input_tokens=None,
                    output_tokens=None,
                    cached_tokens=None,
                    tokens=None,
                    requests=None,
                    unpriced_requests=None,
                )
            )
        else:
            series_points.append(UsagePoint(start=point_start, **points[key].figures()))
    days_in_month = calendar.monthrange(w.today.year, w.today.month)[1]
    # Elapsed days, fractional; a quarter-day floor keeps the first hours from projecting
    # a few cents into a large month, as the reference's projection does.
    elapsed = max(0.25, (now - w.month_start).total_seconds() / 86400)
    spent = round(month.cost_usd, 6)
    return UsageSeries(
        period=period,
        bucket="hour" if hourly else "day",
        timezone=zone.key,
        agent_id=agent_id,
        prices_as_of=PRICES_AS_OF,
        window=UsageWindow(start=w.start, end=now),
        previous=UsagePreviousWindow(
            start=w.previous_start, end=w.previous_end, **previous.figures()
        ),
        points=series_points,
        totals=UsageFigures(**totals.figures()),
        month=UsageMonth(
            start=w.month_start,
            spent_usd=spent,
            projected_usd=round(spent / elapsed * days_in_month, 6),
            days_in_month=days_in_month,
            day_of_month=w.today.day,
            unpriced_requests=month.unpriced_requests,
        ),
    )


def _rank_key(figures: UsageRankAgent | UsageRankModel) -> tuple[float, int]:
    return (-(figures.cost_usd if figures.cost_usd is not None else -1.0), -figures.tokens)


async def usage_rank(
    session: AsyncSession,
    owner_id: str,
    period: UsagePeriod,
    zone: ZoneInfo,
    now: datetime,
    agent_id: str | None = None,
) -> UsageRank:
    """The period's usage per agent and per model, most costly first, then most tokens."""
    w = windows(period, zone, now)
    groups = await usage_groups(
        session, owner_id, w.start, now + timedelta(microseconds=1), None, agent_id
    )
    names = {
        row.id: row.name
        for row in await session.scalars(select(AgentRow).where(AgentRow.owner_id == owner_id))
    }
    totals = Tally()
    agents: dict[str | None, Tally] = {}
    models: dict[tuple[str, str], Tally] = {}
    for row in groups:
        totals.add(row)
        agents.setdefault(row["agent_id"], Tally()).add(row)
        models.setdefault((row["provider"] or "", row["model"] or ""), Tally()).add(row)
    agent_rows = sorted(
        (
            UsageRankAgent(
                agent_id=key,
                agent_name=names.get(key) if key else None,
                **tally.figures(),
            )
            for key, tally in agents.items()
        ),
        key=_rank_key,
    )
    model_rows: list[UsageRankModel] = []
    for (provider, model), tally in models.items():
        figures = tally.figures()
        if tally.requests == tally.unpriced_requests:
            figures["cost_usd"] = None
        model_rows.append(UsageRankModel(provider=provider, model=model, **figures))
    model_rows.sort(key=_rank_key)
    return UsageRank(
        period=period,
        timezone=zone.key,
        agent_id=agent_id,
        prices_as_of=PRICES_AS_OF,
        window=UsageWindow(start=w.start, end=now),
        totals=UsageFigures(**totals.figures()),
        agents=agent_rows,
        models=model_rows,
    )


async def usage_days(
    session: AsyncSession,
    owner_id: str,
    days: int,
    zone: ZoneInfo,
    now: datetime,
    agent_id: str | None = None,
) -> tuple[datetime, list[UsageDay]]:
    """One bucket per local day for the last ``days`` days, today included (so far)."""
    today = now.astimezone(zone).date()
    since = _midnight(today - timedelta(days=days - 1), zone)
    buckets = {today - timedelta(days=k): Tally() for k in range(days - 1, -1, -1)}
    for row in await usage_groups(
        session, owner_id, since, now + timedelta(microseconds=1), zone, agent_id
    ):
        tally = buckets.get(row["local_hour"].date())
        if tally is not None:
            tally.add(row)
    return since, [UsageDay(date=day, **tally.figures()) for day, tally in buckets.items()]


def series_csv(series: UsageSeries) -> str:
    """The series as CSV with a UTF-8 BOM: ``date`` (or ``hour``), cost_usd, tokens,
    requests; the hours that have not started are left out."""
    hourly = series.bucket == "hour"
    lines = [("hour" if hourly else "date") + ",cost_usd,tokens,requests"]
    for point in series.points:
        if point.requests is None:
            continue
        local = point.start.astimezone(ZoneInfo(series.timezone))
        label = local.strftime("%Y-%m-%d %H:00" if hourly else "%Y-%m-%d")
        lines.append(f"{label},{point.cost_usd or 0:.4f},{point.tokens},{point.requests}")
    return "\ufeff" + "\r\n".join(lines) + "\r\n"
