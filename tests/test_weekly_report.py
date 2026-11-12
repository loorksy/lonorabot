"""The weekly report (VISION 5.5.6, 11.3): one wake per agent at the weekly close, the
report in its own conversation, and the reports in the first morning brief after it."""

import json
from datetime import UTC, datetime, timedelta
from typing import Any

import pytest
from lonora_agent.context.routine import wake_context
from lonora_core.run_state import is_conversational
from lonora_db.client import Database
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.schema import (
    AgentRow,
    MessageRow,
    MorningBriefRow,
    RunRow,
    SettingRow,
    ThreadRow,
    TradingJournalRow,
)
from lonora_trading.morning_brief import TRIGGER as BRIEF_TRIGGER
from lonora_trading.morning_brief import brief_tick, latest_close, plain_brief
from lonora_trading.weekly_report import TRIGGER, weekly_tick
from sqlalchemy import select
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]
# Friday 2026-11-13 17:00 New York (EST, UTC-5) is 22:00 UTC.
CLOSE = datetime(2026, 11, 13, 22, tzinfo=UTC)


def facts_of(prompt: str, tag: str) -> dict[str, Any]:
    return json.loads(prompt.split("<" + tag + ">\n", 1)[1].rsplit("\n</" + tag + ">", 1)[0])


def test_the_weekly_close_is_friday_17_00_new_york_and_an_empty_report_is_not_accepted() -> None:
    week = latest_close(CLOSE + timedelta(minutes=1))
    assert week is not None and week[1] == CLOSE
    assert week[0] == datetime(2026, 11, 8, 22, tzinfo=UTC)
    before = latest_close(CLOSE - timedelta(minutes=1))
    assert before is not None and before[1] == CLOSE - timedelta(days=7)
    assert is_conversational(TRIGGER)
    # The facts hold symbols agents typed: the wake is the run's request turn (6.10).
    run = RunRow(thread_id="t", agent_id="a", trigger=TRIGGER, prompt="Report.")
    assert wake_context(run) == "<wake trigger='weekly_report' request='in_the_conversation_turn'/>"


async def runs(db: Database, trigger: str) -> list[RunRow]:
    async with db.sessions() as session:
        return list(
            await session.scalars(
                select(RunRow).where(RunRow.trigger == trigger).order_by(RunRow.created_at)
            )
        )


@pytest.mark.asyncio
async def test_each_agent_is_woken_once_per_week_in_its_own_conversation(task_db: Fixture) -> None:
    db, owner, fixture_agent, _thread = task_db
    async with db.sessions() as session, session.begin():
        lonora = await ensure_personal_agent(session, owner)
        gold = AgentRow(owner_id=owner, name="Gold", created_at=CLOSE - timedelta(days=30))
        resting = AgentRow(
            owner_id=owner, name="Resting", paused=True, created_at=CLOSE - timedelta(days=30)
        )
        late = AgentRow(owner_id=owner, name="Late", created_at=CLOSE + timedelta(hours=1))
        session.add_all([gold, resting, late])
        for agent_id in (lonora.id, fixture_agent):
            row = await session.get(AgentRow, agent_id)
            assert row is not None
            row.created_at = CLOSE - timedelta(days=30)
        await session.flush()
        for identifier, when, status in (
            ("in-week", CLOSE - timedelta(days=1), "confirmed"),
            ("last-week", CLOSE - timedelta(days=8), "confirmed"),
            ("uncertain", CLOSE - timedelta(hours=2), "ambiguous"),
        ):
            session.add(
                TradingJournalRow(
                    operation_id=identifier,
                    owner_id=owner,
                    account_id="acc",
                    request_hash="h",
                    request={"action": "buy", "symbol": "XAUUSD", "volume": "0.1"},
                    status=status,
                    result={"details": {"execution": {"agent_id": gold.id}}},
                    updated_at=when,
                )
            )
    assert await weekly_tick(db, owner, now=CLOSE - timedelta(minutes=1)) == "2026-11-06"
    async with db.sessions() as session, session.begin():
        # Start from the week of the test: drop the previous week's wakes.
        for run in await session.scalars(select(RunRow)):
            await session.delete(run)
    assert await weekly_tick(db, owner, now=CLOSE + timedelta(minutes=1)) == "2026-11-13"
    # Downtime and repeated ticks: one wake per agent for this close.
    assert await weekly_tick(db, owner, now=CLOSE + timedelta(days=2)) is None
    woken = await runs(db, TRIGGER)
    async with db.sessions() as session:
        agents = {row.id: row.name for row in await session.scalars(select(AgentRow))}
        names = {agents[run.agent_id]: run for run in woken}
        assert sorted(names) == sorted(["Lonora", "Gold", "Task fixture"])
        for run in woken:
            thread = await session.get(ThreadRow, run.thread_id)
            assert thread is not None and thread.agent_id == run.agent_id
            assert thread.purpose == "conversation"
    gold_facts = facts_of(names["Gold"].prompt, "week_facts")
    assert gold_facts["operations"] == [
        {"action": "buy", "symbol": "XAUUSD", "volume": "0.1", "state": "confirmed"},
        {"action": "buy", "symbol": "XAUUSD", "volume": "0.1", "state": "awaiting_broker"},
    ]
    assert facts_of(names["Lonora"].prompt, "week_facts")["operations"] == []
    assert "post one line that says so" in names["Lonora"].prompt


@pytest.mark.asyncio
async def test_the_first_brief_after_the_close_carries_the_reports_once(task_db: Fixture) -> None:
    db, owner, fixture_agent, _thread = task_db
    async with db.sessions() as session, session.begin():
        lonora = await ensure_personal_agent(session, owner)
        resting = AgentRow(owner_id=owner, name="Resting", paused=True)
        session.add(resting)
        for agent_id in (lonora.id, fixture_agent):
            row = await session.get(AgentRow, agent_id)
            assert row is not None
            row.created_at = CLOSE - timedelta(days=30)
        resting.created_at = CLOSE - timedelta(days=30)
    await weekly_tick(db, owner, now=CLOSE + timedelta(minutes=1))
    woken = {run.agent_id: run for run in await runs(db, TRIGGER)}
    async with db.sessions() as session, session.begin():
        run = await session.get(RunRow, woken[fixture_agent].id)
        assert run is not None
        session.add(
            MessageRow(
                id="report-1",
                thread_id=run.thread_id,
                agent_id=fixture_agent,
                seq=1,
                role="assistant",
                content="No closed trade this week.",
            )
        )
        run.status = "completed"
        run.model_metadata = {**run.model_metadata, "result_message_id": "report-1"}
    # Saturday 07:01 UTC (no reach-me zone stored): the first brief after the close.
    saturday = datetime(2026, 11, 14, 7, 1, tzinfo=UTC)
    await brief_tick(db, owner, now=saturday)
    (brief,) = await runs(db, BRIEF_TRIGGER)
    assert "summarize the agents' weekly reports" in brief.prompt
    reports = {
        item["agent"]: item for item in facts_of(brief.prompt, "brief_facts")["weekly_reports"]
    }
    assert reports["Task fixture"] == {
        "agent": "Task fixture",
        "state": "posted",
        "report": "No closed trade this week.",
    }
    assert reports["Lonora"]["state"] == "not_ready"
    assert reports["Resting"]["state"] == "paused"
    plain = plain_brief(facts_of(brief.prompt, "brief_facts"), "ar")
    assert "تقارير الأسبوع:" in plain
    assert "• Task fixture: نُشر في محادثته" in plain and "• Resting: موقوف مؤقتاً، لا تقرير" in plain
    async with db.sessions() as session, session.begin():
        stored = await session.get(RunRow, brief.id)
        assert stored is not None
        stored.status = "completed"
        stored.model_metadata = {**stored.model_metadata, "result_message_id": "m"}
    await brief_tick(db, owner, now=saturday + timedelta(minutes=1))
    # The next day's brief no longer carries them.
    await brief_tick(db, owner, now=saturday + timedelta(days=1))
    second = (await runs(db, BRIEF_TRIGGER))[-1]
    assert second.id != brief.id
    assert facts_of(second.prompt, "brief_facts")["weekly_reports"] == []
    assert "weekly reports" not in second.prompt
    async with db.sessions() as session:
        record = await session.get(MorningBriefRow, owner)
        assert record is not None and record.weekly is not None
        assert record.weekly["summarized"] is True


@pytest.mark.asyncio
async def test_a_brief_at_the_close_waits_for_the_reports_and_names_a_missing_one(
    task_db: Fixture,
) -> None:
    db, owner, fixture_agent, _thread = task_db
    async with db.sessions() as session, session.begin():
        lonora = await ensure_personal_agent(session, owner)
        for agent_id in (lonora.id, fixture_agent):
            row = await session.get(AgentRow, agent_id)
            assert row is not None
            row.created_at = CLOSE - timedelta(days=30)
        # Tokyo: the close (Friday 17:00 New York) is Saturday 07:00, the brief time.
        session.add(
            SettingRow(key="incoming-call-policy:" + owner, payload={"timezone": "Asia/Tokyo"})
        )
    at = CLOSE + timedelta(seconds=10)
    # The agents are not woken yet: the brief waits.
    assert await brief_tick(db, owner, now=at) is None
    await weekly_tick(db, owner, now=at)
    # Reports are being written: the brief still waits.
    assert await brief_tick(db, owner, now=at + timedelta(minutes=5)) is None
    assert await runs(db, BRIEF_TRIGGER) == []
    woken = {run.agent_id: run for run in await runs(db, TRIGGER)}
    async with db.sessions() as session, session.begin():
        for run_id in (woken[lonora.id].id, woken[fixture_agent].id):
            run = await session.get(RunRow, run_id)
            assert run is not None
            run.status = "completed"
    # Every report run ended (here with no message): the brief goes and says so.
    assert await brief_tick(db, owner, now=at + timedelta(minutes=6)) == "2026-11-14"
    (brief,) = await runs(db, BRIEF_TRIGGER)
    states = {
        item["agent"]: item["state"]
        for item in facts_of(brief.prompt, "brief_facts")["weekly_reports"]
    }
    assert states == {"Lonora": "no_report", "Task fixture": "no_report"}
