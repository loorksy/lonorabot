from datetime import date, datetime
from typing import Literal

from pydantic import Field

from .domain import Contract


class TokenUsage(Contract):
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    cached_tokens: int = Field(default=0, ge=0)


# --- Usage dashboard (WP-I; owner decisions D4 and Q22: a view, never a cap) ----------

UsagePeriod = Literal["day", "week", "month"]
UsageBucket = Literal["hour", "day"]


class UsageFigures(Contract):
    """Usage of a set of requests. ``input_tokens`` counts every prompt token, cached
    included; ``cached_tokens`` is the part served from the provider's cache;
    ``tokens`` is input plus output. ``cost_usd`` sums the requests whose model has a
    list price; ``unpriced_requests`` counts the others, whose cost is unknown."""

    cost_usd: float = 0.0
    input_tokens: int = 0
    output_tokens: int = 0
    cached_tokens: int = 0
    tokens: int = 0
    requests: int = 0
    unpriced_requests: int = 0


class UsageWindow(Contract):
    start: datetime
    end: datetime


class UsagePreviousWindow(UsageFigures):
    """The equal preceding window, cut at the same elapsed point as the current one."""

    start: datetime
    end: datetime


class UsagePoint(Contract):
    """One hour or day; every figure is ``None`` for an hour that has not started."""

    start: datetime
    cost_usd: float | None
    input_tokens: int | None
    output_tokens: int | None
    cached_tokens: int | None
    tokens: int | None
    requests: int | None
    unpriced_requests: int | None


class UsageMonth(Contract):
    """Month to date and its linear projection; no limit exists (D4)."""

    start: datetime
    spent_usd: float
    projected_usd: float
    days_in_month: int
    day_of_month: int
    unpriced_requests: int


class UsageSeries(Contract):
    period: UsagePeriod
    bucket: UsageBucket
    timezone: str
    agent_id: str | None
    prices_as_of: str
    window: UsageWindow
    previous: UsagePreviousWindow
    points: list[UsagePoint]
    totals: UsageFigures
    month: UsageMonth


class UsageRankAgent(UsageFigures):
    agent_id: str | None
    agent_name: str | None


class UsageRankModel(UsageFigures):
    """``cost_usd`` is ``None`` when the model has no list price."""

    provider: str
    model: str
    cost_usd: float | None = None  # pyright: ignore[reportIncompatibleVariableOverride]


class UsageRank(Contract):
    period: UsagePeriod
    timezone: str
    agent_id: str | None
    prices_as_of: str
    window: UsageWindow
    totals: UsageFigures
    agents: list[UsageRankAgent]
    models: list[UsageRankModel]


class UsageDay(UsageFigures):
    date: date
