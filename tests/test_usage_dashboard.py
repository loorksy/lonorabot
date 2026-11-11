"""Usage dashboard data (WP-I; owner decisions D4 and Q22: a view, never a cap).

The pure cases run everywhere: list prices, cached tokens counted once, the previous
equal window and the CSV. The PostgreSQL cases (LONORA_DATABASE_URL) seed ``ln_usage``
rows at controlled times and read them through ``lonora_db.usage`` and the API: hourly
and daily buckets in the owner's zone, the previous window cut at the same elapsed
point, unpriced models, the month projection, ranking, the agent filter and owner scope.
"""

import math
import os
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from lonora_contracts.domain import utcnow
from lonora_contracts.usage import UsagePoint, UsageSeries
from lonora_core.model_pricing import model_price, prompt_tokens, usage_cost
from lonora_db.usage import series_csv, windows

RIYADH = ZoneInfo("Asia/Riyadh")  # UTC+3, no daylight saving
# 2030-03-15 10:30 in Riyadh; far from the real clock, so other rows never fall inside.
NOW = datetime(2030, 3, 15, 10, 30, tzinfo=RIYADH).astimezone(UTC)
SONNET = ("anthropic", "claude-sonnet-4-5", 1000, 500, 2000)  # input excludes cached
GPT4O = ("openai", "gpt-4o", 3000, 100, 1000)  # prompt_tokens includes cached
UNKNOWN = ("openai", "gpt-9-imaginary", 10, 10, 0)


@pytest.fixture(autouse=True)
def openai_test_price(monkeypatch: pytest.MonkeyPatch) -> None:
    """The production table has no unverified OpenAI prices; these tests use a test-only
    OpenAI row to exercise the provider that counts cached tokens inside its input."""
    from lonora_core import model_pricing

    monkeypatch.setitem(
        model_pricing._PRICES,  # pyright: ignore[reportPrivateUsage]
        "openai",
        {"gpt-4o": model_pricing.ModelPrice(2.50, 1.25, 10.00)},
    )


SONNET_COST = (1000 * 3 + 2000 * 0.3 + 500 * 15) / 1e6
GPT4O_COST = (2000 * 2.5 + 1000 * 1.25 + 100 * 10) / 1e6


def near(
    value: float | None, expected: float, rel_tol: float = 1e-6, abs_tol: float = 1e-9
) -> bool:
    return value is not None and math.isclose(value, expected, rel_tol=rel_tol, abs_tol=abs_tol)


# --- Prices -------------------------------------------------------------------------


def test_cached_tokens_are_priced_once_at_the_cached_rate():
    assert near(usage_cost(*SONNET), SONNET_COST)
    assert near(usage_cost(*GPT4O), GPT4O_COST)
    # Anthropic reports input without the cache reads; OpenAI-compatible APIs include them.
    assert prompt_tokens("anthropic", 1000, 2000) == 3000
    assert prompt_tokens("openai", 3000, 1000) == 3000


def test_unknown_models_have_no_price_and_variants_are_not_guessed():
    assert usage_cost(*UNKNOWN) is None
    assert model_price("openrouter", "anthropic/claude-sonnet-4.5") is None
    assert model_price("openai", "gpt-5-pro") is None
    assert model_price("anthropic", "claude-sonnet-4-5-preview") is None
    assert model_price("fake", "fake-model") is None
    # A dated snapshot of a listed model is that model.
    assert model_price("anthropic", "claude-sonnet-4-5-20250929") == model_price(
        "anthropic", "claude-sonnet-4-5"
    )
    # Only Anthropic's dated ids are its listed model; another provider's snapshot is
    # unpriced unless it has its own row.
    assert model_price("openai", "gpt-4o-2024-05-13") is None
    assert model_price("openai", "gpt-4o-mini") != model_price("openai", "gpt-4o")


# --- Windows and CSV -----------------------------------------------------------------


def test_previous_window_has_equal_length_and_the_same_elapsed_point():
    day = windows("day", RIYADH, NOW)
    assert day.start == datetime(2030, 3, 15, tzinfo=RIYADH)
    assert day.previous_start == datetime(2030, 3, 14, tzinfo=RIYADH)
    assert day.previous_end == datetime(2030, 3, 14, 10, 30, tzinfo=RIYADH)
    week = windows("week", RIYADH, NOW)
    assert week.start == datetime(2030, 3, 9, tzinfo=RIYADH)
    assert week.previous_start == datetime(2030, 3, 2, tzinfo=RIYADH)
    assert week.previous_end == datetime(2030, 3, 8, 10, 30, tzinfo=RIYADH)
    assert NOW - week.start == week.previous_end - week.previous_start
    month = windows("month", RIYADH, NOW)
    assert month.start == datetime(2030, 2, 14, tzinfo=RIYADH)
    assert month.month_start == datetime(2030, 3, 1, tzinfo=RIYADH)


def _point(start: datetime, cost: float | None, tokens: int | None) -> UsagePoint:
    filled = None if tokens is None else 0
    return UsagePoint(
        start=start,
        cost_usd=cost,
        input_tokens=filled,
        output_tokens=filled,
        cached_tokens=filled,
        tokens=tokens,
        requests=None if tokens is None else 2,
        unpriced_requests=filled,
    )


def test_csv_has_a_bom_and_leaves_out_hours_not_started():
    series = UsageSeries.model_validate(
        {
            "period": "day",
            "bucket": "hour",
            "timezone": "Asia/Riyadh",
            "agent_id": None,
            "prices_as_of": "2026-11-10",
            "window": {"start": datetime(2030, 3, 15, tzinfo=RIYADH), "end": NOW},
            "previous": {
                "start": datetime(2030, 3, 14, tzinfo=RIYADH),
                "end": datetime(2030, 3, 14, 10, 30, tzinfo=RIYADH),
            },
            "points": [
                _point(datetime(2030, 3, 15, 9, tzinfo=RIYADH), 0.0111, 3500),
                _point(datetime(2030, 3, 15, 23, tzinfo=RIYADH), None, None),
            ],
            "totals": {},
            "month": {
                "start": datetime(2030, 3, 1, tzinfo=RIYADH),
                "spent_usd": 0,
                "projected_usd": 0,
                "days_in_month": 31,
                "day_of_month": 15,
                "unpriced_requests": 0,
            },
        }
    )
    assert (
        series_csv(series) == "﻿hour,cost_usd,tokens,requests\r\n2030-03-15 09:00,0.0111,3500,2\r\n"
    )


# --- PostgreSQL ------------------------------------------------------------------------


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The usage dashboard cases use the real migrated PostgreSQL schema.")


async def seed(fixture: Any, rows: list[tuple[str, tuple[Any, ...], datetime]]) -> None:
    from lonora_db.schema import UsageRow

    async with fixture.runtime.db.sessions() as session, session.begin():
        for agent_id, (provider, model, inp, out, cached), at in rows:
            session.add(
                UsageRow(
                    owner_id=fixture.owner,
                    agent_id=agent_id,
                    payload={
                        "run_id": uuid4().hex,
                        "provider": provider,
                        "model": model,
                        "input_tokens": inp,
                        "output_tokens": out,
                        "cached_tokens": cached,
                    },
                    created_at=at.astimezone(UTC),
                    updated_at=at.astimezone(UTC),
                )
            )


def local(*parts: int) -> datetime:
    return datetime(*parts, tzinfo=RIYADH)  # pyright: ignore[reportArgumentType]


@pytest.mark.asyncio
async def test_series_rank_and_days_from_seeded_rows():
    database()
    from check_streaming import Fixture
    from lonora_db.usage import usage_days, usage_rank, usage_series

    fixture = await Fixture().open()
    try:
        a = (await fixture.agent("Usage A"))["id"]
        b = (await fixture.agent("Usage B"))["id"]
        await seed(
            fixture,
            [
                (a, SONNET, local(2030, 3, 15, 9, 10)),
                # 00:05 in Riyadh is still the 14th in UTC: it belongs to today's hour 0.
                (a, SONNET, local(2030, 3, 15, 0, 5)),
                (b, GPT4O, local(2030, 3, 14, 23, 50)),  # yesterday after 10:30
                (b, GPT4O, local(2030, 3, 14, 8, 0)),  # yesterday before 10:30
                (b, UNKNOWN, local(2030, 3, 15, 10, 20)),  # the current hour
                (a, SONNET, local(2030, 3, 1, 12, 0)),  # first day of the month
                (a, SONNET, local(2030, 2, 20, 12, 0)),  # last 30 days, not this month
                (a, SONNET, local(2030, 3, 15, 10, 40)),  # after now: never counted
                (b, GPT4O, local(2030, 2, 5, 12, 0)),  # the previous 30 days
            ],
        )
        async with fixture.runtime.db.sessions() as session:
            day = await usage_series(session, fixture.owner, "day", RIYADH, NOW)
            week = await usage_series(session, fixture.owner, "week", RIYADH, NOW)
            month = await usage_series(session, fixture.owner, "month", RIYADH, NOW)
            only_a = await usage_series(session, fixture.owner, "day", RIYADH, NOW, a)
            utc_day = await usage_series(session, fixture.owner, "day", ZoneInfo("UTC"), NOW)
            rank = await usage_rank(session, fixture.owner, "week", RIYADH, NOW)
            since, days = await usage_days(session, fixture.owner, 7, RIYADH, NOW, a)
            stranger = await usage_series(session, "not-this-owner", "month", RIYADH, NOW)

        # Today in hours: 24 points, the hours after 10:00 are absent (null).
        assert day.bucket == "hour" and len(day.points) == 24
        assert day.points[0].start == local(2030, 3, 15, 0)
        assert near(day.points[0].cost_usd, SONNET_COST)
        assert near(day.points[9].cost_usd, SONNET_COST)
        assert day.points[10].requests == 1 and day.points[10].unpriced_requests == 1
        assert day.points[10].cost_usd == 0
        assert day.points[5].requests == 0 and day.points[5].cost_usd == 0
        assert all(point.requests is None for point in day.points[11:])
        assert near(day.totals.cost_usd, 2 * SONNET_COST)
        assert day.totals.requests == 3 and day.totals.unpriced_requests == 1
        # Input counts every prompt token, cached included, for every provider.
        assert day.totals.input_tokens == 3000 + 3000 + 10
        assert day.totals.cached_tokens == 4000 and day.totals.output_tokens == 1010
        assert day.totals.tokens == 6010 + 1010
        # Yesterday up to 10:30 only.
        assert day.previous.requests == 1
        assert near(day.previous.cost_usd, GPT4O_COST)
        assert day.window.start == local(2030, 3, 15) and day.window.end == NOW

        # The same instant read in UTC: 00:05 Riyadh is the 14th, outside UTC's today.
        assert utc_day.timezone == "UTC" and utc_day.totals.requests == 2

        # Last 7 days in days, today so far included.
        assert week.bucket == "day" and len(week.points) == 7
        assert week.points[0].start == local(2030, 3, 9)
        assert near(week.points[-2].cost_usd, 2 * GPT4O_COST)
        assert near(week.points[-1].cost_usd, 2 * SONNET_COST)
        assert near(week.totals.cost_usd, 2 * SONNET_COST + 2 * GPT4O_COST)
        assert week.previous.requests == 0 and week.previous.cost_usd == 0

        # Last 30 days, against the 30 before; the month to date and its projection.
        assert len(month.points) == 30
        assert near(month.totals.cost_usd, 4 * SONNET_COST + 2 * GPT4O_COST)
        assert near(month.previous.cost_usd, GPT4O_COST)
        assert month.month.start == local(2030, 3, 1)
        assert month.month.days_in_month == 31 and month.month.day_of_month == 15
        # This month: today (rows 1, 2), the 1st (row 6) and yesterday (rows 3, 4).
        spent = 3 * SONNET_COST + 2 * GPT4O_COST
        assert near(month.month.spent_usd, spent)
        assert month.month.unpriced_requests == 1
        elapsed = 14 + 10.5 / 24
        assert near(month.month.projected_usd, spent / elapsed * 31, rel_tol=1e-5)

        # One agent.
        assert only_a.agent_id == a and only_a.totals.requests == 2
        assert only_a.totals.unpriced_requests == 0 and only_a.previous.requests == 0

        # Ranking: by cost, then tokens; the unknown model has no cost and comes last.
        assert [item.agent_id for item in rank.agents] == [a, b]
        assert rank.agents[0].agent_name and rank.agents[0].agent_name.startswith("Usage A")
        assert rank.agents[1].unpriced_requests == 1
        assert near(rank.agents[1].cost_usd, 2 * GPT4O_COST)
        assert [(item.provider, item.model) for item in rank.models] == [
            ("anthropic", "claude-sonnet-4-5"),
            ("openai", "gpt-4o"),
            ("openai", "gpt-9-imaginary"),
        ]
        assert rank.models[2].cost_usd is None and rank.models[2].requests == 1

        # The model page's 7 days of one agent.
        assert since == local(2030, 3, 9)
        assert [item.date for item in days][-1] == date(2030, 3, 15)
        assert near(days[-1].cost_usd, 2 * SONNET_COST) and days[-1].requests == 2
        assert sum(item.requests for item in days) == 2

        # Another owner's view never includes these rows.
        assert stranger.totals.requests == 0 and stranger.month.spent_usd == 0
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_usage_routes_serve_series_rank_csv_and_day_buckets():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = (await fixture.agent("Usage route"))["id"]
        await seed(fixture, [(agent, SONNET, utcnow() - timedelta(seconds=5))])
        query = f"period=day&agent_id={agent}&tz=UTC"
        series = await fixture.request("GET", "/usage/series?" + query)
        assert series["bucket"] == "hour" and series["timezone"] == "UTC"
        assert series["totals"]["requests"] == 1
        assert near(series["totals"]["cost_usd"], SONNET_COST)
        assert set(series["month"]) == {
            "start",
            "spent_usd",
            "projected_usd",
            "days_in_month",
            "day_of_month",
            "unpriced_requests",
        }
        rank = await fixture.request("GET", "/usage/rank?" + query)
        assert rank["agents"][0]["agent_id"] == agent
        assert rank["models"][0]["model"] == "claude-sonnet-4-5"

        response = await fixture.client.get("/api/usage/export.csv?" + query)
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/csv")
        assert "attachment" in response.headers["content-disposition"]
        text = response.content.decode("utf-8")
        assert text.startswith("﻿hour,cost_usd,tokens,requests\r\n")
        rows = [line.split(",") for line in text.lstrip("﻿").splitlines()[1:]]
        assert sum(int(row[3]) for row in rows) == 1
        assert near(sum(float(row[1]) for row in rows), SONNET_COST, abs_tol=1e-4)

        report = await fixture.request(
            "GET", f"/usage/agents?days=7&bucket=day&agent_id={agent}&tz=UTC"
        )
        assert report["bucket"] == "day" and len(report["buckets"]) == 7
        assert report["buckets"][-1]["requests"] == 1
        assert near(report["buckets"][-1]["cost_usd"], SONNET_COST)
        assert near(report["agents"][0]["cost_usd"], SONNET_COST)
        assert near(report["agents"][0]["models"][0]["cost_usd"], SONNET_COST)
        # Without a bucket the report keeps its shape, with costs added.
        plain = await fixture.request("GET", f"/usage/agents?days=30&agent_id={agent}")
        assert "buckets" not in plain and plain["agents"][0]["unpriced_requests"] == 0

        bad = await fixture.client.get("/api/usage/series?period=day&tz=Mars/Olympus")
        assert bad.status_code == 422
        assert (await fixture.client.get("/api/usage/series?period=year")).status_code == 422
        # A zone directory is not a zone: 422, never a server error.
        folder = await fixture.client.get("/api/usage/series?period=day&tz=America")
        assert folder.status_code == 422 and folder.json()["code"] == "invalid_timezone"
    finally:
        await fixture.close()
