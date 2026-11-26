"""Routine runs do not stack, and a late run knows it is late (VISION 11.5, 11.6, 17, 5.2).

A recurring routine whose earlier run is still queued (retry backoff included), leased or
running gets no second run when it comes due: its schedule advances and the skipped
occurrence is counted, and its next run carries the count. A run waiting for the owner's
answer does not hold the schedule, and a one-shot always fires. Every routine run carries
when it was due and how many later occurrences were folded into it; one that starts more
than 15 minutes after it was due is told so in one fixed server sentence (6.10).
"""

import os
from datetime import UTC, datetime, timedelta
from typing import Any, cast

import pytest


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The routine overlap cases use the real migrated PostgreSQL schema.")


async def make_due(fixture: Any, routine_id: str, at: datetime) -> None:
    from lonora_db.schema import RoutineRow

    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(RoutineRow, routine_id, with_for_update=True)
        assert row is not None
        row.next_run_at = at


async def fire(fixture: Any, routine_id: str) -> bool:
    """One dispatch pass for this routine (``dispatch_routines`` calls it per due routine)."""
    from lonora_db.routines import enqueue_one

    async with fixture.runtime.db.sessions() as session, session.begin():
        return await enqueue_one(session, routine_id)


async def runs_of(fixture: Any, routine_id: str) -> list[Any]:
    from lonora_db.schema import RunRow
    from sqlalchemy import select

    async with fixture.runtime.db.sessions() as session:
        return list(
            await session.scalars(
                select(RunRow)
                .where(RunRow.model_metadata["routine_id"].as_string() == routine_id)
                .order_by(RunRow.created_at)
            )
        )


async def set_run(fixture: Any, run_id: str, status: str, **values: Any) -> None:
    from lonora_db.schema import RunRow

    async with fixture.runtime.db.sessions() as session, session.begin():
        run = await session.get(RunRow, run_id, with_for_update=True)
        assert run is not None
        run.status = status
        for key, value in values.items():
            setattr(run, key, value)


async def skipped(fixture: Any, routine_id: str) -> int:
    from lonora_db.schema import RoutineRow

    async with fixture.runtime.db.sessions() as session:
        row = await session.get(RoutineRow, routine_id)
        assert row is not None
        return row.skipped_occurrences


async def routine(fixture: Any, name: str, **schedule: Any) -> dict[str, Any]:
    agent = await fixture.agent(name)
    return await fixture.request(
        "POST", f"/routines/{agent['id']}", {"prompt": "Check gold", **schedule}
    )


@pytest.mark.asyncio
async def test_a_running_routine_skips_its_ticks_and_its_next_run_carries_the_count():
    database()
    from check_streaming import Fixture
    from lonora_automation.delivery import routine_history
    from lonora_contracts.domain import utcnow

    fixture = await Fixture().open()
    try:
        made = await routine(fixture, "Overlap", interval_seconds=60)
        await make_due(fixture, made["id"], utcnow() - timedelta(seconds=1))
        assert await fire(fixture, made["id"])
        [first] = await runs_of(fixture, made["id"])
        await set_run(
            fixture,
            first.id,
            "running",
            lease_owner="worker",
            lease_expires_at=utcnow() + timedelta(minutes=5),
        )
        # Two more dispatch passes while it runs: no second run, two counted skips.
        for _ in range(2):
            await make_due(fixture, made["id"], utcnow() - timedelta(seconds=1))
            assert not await fire(fixture, made["id"])
        assert [run.id for run in await runs_of(fixture, made["id"])] == [first.id]
        assert await skipped(fixture, made["id"]) == 2
        # The schedule kept moving: the routine is not due again until its next tick.
        listed = cast(
            list[Any], await fixture.request("GET", f"/routines?agent_id={made['agent_id']}")
        )
        assert datetime.fromisoformat(listed[0]["next_run_at"]) > utcnow()
        # Once the first run ends, the next tick fires and carries the skipped count.
        await set_run(fixture, first.id, "completed", lease_owner=None, lease_expires_at=None)
        await make_due(fixture, made["id"], utcnow() - timedelta(seconds=1))
        assert await fire(fixture, made["id"])
        first, second = await runs_of(fixture, made["id"])
        assert second.model_metadata["skipped_occurrences"] == 2
        assert second.model_metadata["missed_occurrences"] == 0
        assert "scheduled_for" in second.model_metadata
        assert await skipped(fixture, made["id"]) == 0
        # The routine's history shows the count on the run that carried it.
        history = await routine_history(fixture.runtime.db, made["id"], fixture.owner)
        assert [run["id"] for run in history] == [second.id, first.id]
        assert history[0]["model_metadata"]["skipped_occurrences"] == 2
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_run_in_retry_backoff_holds_the_schedule_for_five_minutes():
    database()
    from check_streaming import Fixture
    from lonora_contracts.domain import utcnow
    from lonora_db.routines import enqueue_routine
    from lonora_db.schema import RoutineRow

    fixture = await Fixture().open()
    try:
        made = await routine(fixture, "Backoff", interval_seconds=60)
        start = utcnow()
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RoutineRow, made["id"], with_for_update=True)
            assert row is not None
            row.next_run_at = start
            assert await enqueue_routine(session, row, start)
        [first] = await runs_of(fixture, made["id"])
        # A model outage: the run is queued again, waiting for its retry time.
        retry = {"retry": {"not_before": (start + timedelta(minutes=15)).isoformat()}}
        await set_run(fixture, first.id, "queued", execution_state={"environment": retry})
        for minute in range(1, 6):
            now = start + timedelta(minutes=minute, seconds=1)
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(RoutineRow, made["id"], with_for_update=True)
                assert row is not None and row.next_run_at <= now
                assert not await enqueue_routine(session, row, now)
        assert [run.id for run in await runs_of(fixture, made["id"])] == [first.id]
        assert await skipped(fixture, made["id"]) == 5
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_question_waiting_for_the_owner_does_not_hold_the_schedule():
    database()
    from check_streaming import Fixture
    from lonora_contracts.domain import utcnow

    fixture = await Fixture().open()
    try:
        made = await routine(fixture, "Asking", interval_seconds=60)
        await make_due(fixture, made["id"], utcnow() - timedelta(seconds=1))
        assert await fire(fixture, made["id"])
        [first] = await runs_of(fixture, made["id"])
        await set_run(fixture, first.id, "waiting_input")
        await make_due(fixture, made["id"], utcnow() - timedelta(seconds=1))
        assert await fire(fixture, made["id"])
        assert len(await runs_of(fixture, made["id"])) == 2
        assert await skipped(fixture, made["id"]) == 0
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_one_shot_fires_even_while_an_earlier_run_of_it_is_queued():
    database()
    from check_streaming import Fixture
    from lonora_contracts.domain import utcnow
    from lonora_db.schema import RoutineRow

    fixture = await Fixture().open()
    try:
        made = await routine(fixture, "Once", interval_seconds=60)
        await make_due(fixture, made["id"], utcnow() - timedelta(seconds=1))
        assert await fire(fixture, made["id"])
        # The owner turns it into a one-shot while that run still waits in the queue.
        at = (utcnow() + timedelta(minutes=5)).replace(microsecond=0)
        await fixture.request("PUT", f"/routines/{made['id']}", {"run_at": at.isoformat()})
        await make_due(fixture, made["id"], utcnow() - timedelta(seconds=1))
        assert await fire(fixture, made["id"])
        assert len(await runs_of(fixture, made["id"])) == 2
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(RoutineRow, made["id"])
            assert row is not None and row.enabled is False and row.last_run_at is not None
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_late_routine_run_is_told_when_it_was_due():
    database()
    from check_streaming import Fixture
    from lonora_agent.context.routine import BACKGROUND, wake_context
    from lonora_contracts.domain import utcnow

    fixture = await Fixture().open()
    try:
        late = await routine(fixture, "Late", interval_seconds=3600)
        due = (utcnow() - timedelta(hours=3)).replace(microsecond=0)
        await make_due(fixture, late["id"], due)
        assert await fire(fixture, late["id"])
        [run] = await runs_of(fixture, late["id"])
        assert datetime.fromisoformat(run.model_metadata["scheduled_for"]) == due
        # Fired once for 06:00; 07:00, 08:00 and 09:00 were folded into it.
        assert run.model_metadata["missed_occurrences"] == 3
        assert run.model_metadata["skipped_occurrences"] == 0
        marker = wake_context(run)
        assert BACKGROUND in marker
        assert (
            "This routine run is late: it was due at " + due.strftime("%Y-%m-%d %H:%M UTC")
            in marker
        )
        assert "Later occurrences folded into it: 3." in marker
        assert "Re-check what changed" in marker
        # One that is a minute late is on time: the plain background wake.
        prompt = await routine(fixture, "Prompt", interval_seconds=3600)
        await make_due(fixture, prompt["id"], utcnow() - timedelta(minutes=1))
        assert await fire(fixture, prompt["id"])
        [run] = await runs_of(fixture, prompt["id"])
        assert run.model_metadata["missed_occurrences"] == 0
        assert wake_context(run) == (
            "<wake trigger='routine' request='in_the_conversation_turn'>\n"
            + BACKGROUND
            + "\n</wake>"
        )
    finally:
        await fixture.close()


def test_missed_cron_occurrences_are_counted_up_to_a_bound():
    from lonora_contracts.routines import RoutineCreate
    from lonora_db.routines import MISSED_COUNT_CAP, missed_occurrences

    hourly = RoutineCreate(prompt="p", cron="0 * * * *")
    due = datetime(2026, 11, 26, 6, tzinfo=UTC)
    assert missed_occurrences(hourly, due, due + timedelta(hours=3, seconds=30)) == 3
    assert missed_occurrences(hourly, due, due + timedelta(minutes=59)) == 0
    # A minute-by-minute schedule after a month of downtime stops counting at the bound.
    minutely = RoutineCreate(prompt="p", cron="* * * * *")
    assert missed_occurrences(minutely, due, due + timedelta(days=30)) == MISSED_COUNT_CAP
    every = RoutineCreate(prompt="p", interval_seconds=600)
    assert missed_occurrences(every, due, due + timedelta(minutes=35)) == 3
    once = RoutineCreate(prompt="p", run_at=datetime(2099, 1, 1, tzinfo=UTC))
    assert missed_occurrences(once, due, due + timedelta(days=1)) == 0


@pytest.mark.asyncio
async def test_a_caller_cannot_set_the_routine_timing_of_a_run():
    database()
    from check_streaming import Fixture
    from lonora_contracts.runs import RunRequest
    from lonora_db.runs import create_run

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Forged")
        thread = await fixture.conversation(agent)
        async with fixture.runtime.db.sessions() as session, session.begin():
            run = await create_run(
                session,
                fixture.owner,
                RunRequest(
                    thread_id=thread["id"],
                    agent_id=agent["id"],
                    trigger="routine",
                    metadata={
                        "scheduled_for": "2026-01-01T00:00:00+00:00",
                        "missed_occurrences": 9,
                        "skipped_occurrences": 9,
                    },
                ),
            )
            assert not {"scheduled_for", "missed_occurrences", "skipped_occurrences"} & set(
                run.model_metadata
            )
    finally:
        await fixture.close()
