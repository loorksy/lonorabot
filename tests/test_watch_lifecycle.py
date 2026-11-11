"""A watch the owner believes is gone is gone.

A watch wakes an Agent that may hold a signed mandate, so every way a watch stops has
to hold: ending the Task that created it settles it, a stopped watch is not evaluated,
does not read as live, wakes no waiting Task, and is never handed back to an Agent that
asks for a new one.
"""

from datetime import timedelta
from types import SimpleNamespace
from typing import Any, cast

import pytest
from lonora_adapters.brokers.base import BrokerManager
from lonora_contracts.domain import utcnow
from lonora_contracts.tasks import TaskControl, TaskCreate
from lonora_db.account_authority import stop_management_task
from lonora_db.client import Database
from lonora_db.market_watches import control_watch
from lonora_db.schema import AccountAuthorityRow, EventRow, MarketWatchRow, RunRow, TicketRow
from lonora_db.task_wait import resume_ready_waits
from lonora_db.tasks import complete_task, control_task, create_task, save_task, task_state
from lonora_market import watchers
from lonora_session.idempotency import stable_id
from lonora_tools.context import ToolContext
from lonora_tools.market_watch import identical_watch, keyed_watch
from sqlalchemy import select
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]
NO_BROKERS = cast(BrokerManager, None)
LIVE = {
    "evaluation_status": "active",
    "health": {"state": "healthy"},
    "lifecycle": "pending",
}


def payload(**extra: Any) -> dict[str, Any]:
    return {
        "kind": "price",
        "account_id": "acc",
        "symbol": "EURUSDm",
        "prompt": "Reassess the break",
        "condition": "below",
        "level": "1.11305",
        **extra,
    }


async def task_with_watch(
    db: Database, owner: str, agent: str, thread: str, task_id: str | None = None
) -> tuple[TicketRow, str, str]:
    """A Task, the watch its Run created, and a watch from the conversation."""
    async with db.sessions() as session, session.begin():
        task = await create_task(
            session, owner, agent, thread, TaskCreate(title="Manage the account"), task_id
        )
        state = {
            **LIVE,
            "next_check": (utcnow() + timedelta(seconds=30)).isoformat(),
            "task_id": task.id,
            "task_run_id": task.payload["run_id"],
        }
        owned = MarketWatchRow(
            owner_id=owner, agent_id=agent, thread_id=task.thread_id, payload=payload(), state=state
        )
        other = MarketWatchRow(
            owner_id=owner, agent_id=agent, thread_id=thread, payload=payload(), state=dict(LIVE)
        )
        session.add_all([owned, other])
    return task, owned.id, other.id


async def polled(db: Database, monkeypatch: pytest.MonkeyPatch) -> set[str]:
    """The watches one poll of the evaluator takes."""
    seen: set[str] = set()

    async def check(_: Database, __: BrokerManager, original: MarketWatchRow, *args: Any) -> int:
        seen.add(original.id)
        return 0

    monkeypatch.setattr(watchers, "check_watch", check)
    async with db.sessions() as session, session.begin():
        for row in await session.scalars(select(MarketWatchRow)):
            row.state = {key: value for key, value in row.state.items() if key != "next_check"}
    await watchers.check_watches(db, NO_BROKERS)
    return seen


async def assert_settled(db: Database, owned: str, other: str) -> None:
    async with db.sessions() as session:
        watch = await session.get(MarketWatchRow, owned)
        kept = await session.get(MarketWatchRow, other)
        events = list(
            await session.scalars(select(EventRow).where(EventRow.kind == "market_watches.updated"))
        )
    assert watch is not None and kept is not None
    assert watch.payload["enabled"] is False and watch.state["code"] == "task_terminal"
    # Nothing in the stored state still reads as a live evaluation.
    assert "evaluation_status" not in watch.state and "next_check" not in watch.state
    assert watch.version == 2
    # The owner's lists refresh: the change is an event like any other stop.
    assert [event.payload["id"] for event in events] == [owned]
    # A watch from the conversation is not the Task's to settle.
    assert kept.payload.get("enabled", True) is True and kept.version == 1


@pytest.mark.asyncio
async def test_cancelling_a_task_settles_the_watches_it_created(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, thread = task_db
    task, owned, other = await task_with_watch(db, owner, agent, thread)
    async with db.sessions() as session, session.begin():
        await control_task(
            session,
            owner,
            TaskControl(task_id=task.id, action="cancel", expected_version=task.version),
        )
    await assert_settled(db, owned, other)
    assert await polled(db, monkeypatch) == {other}


@pytest.mark.asyncio
async def test_a_cancel_requested_while_the_run_works_settles_the_watches_at_once(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread = task_db
    task, owned, other = await task_with_watch(db, owner, agent, thread)
    async with db.sessions() as session, session.begin():
        run = await session.get(RunRow, task.payload["run_id"])
        assert run is not None
        run.status = "running"
    async with db.sessions() as session, session.begin():
        row = await control_task(
            session,
            owner,
            TaskControl(task_id=task.id, action="cancel", expected_version=task.version),
        )
        # The worker has not returned yet: the Task is not terminal, the watch already is.
        assert task_state(row).control_requested == "cancel"
    await assert_settled(db, owned, other)


@pytest.mark.asyncio
async def test_completing_a_task_settles_the_watches_it_created(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    task, owned, other = await task_with_watch(db, owner, agent, thread)
    async with db.sessions() as session, session.begin():
        await complete_task(session, owner, task.id, task.version)
    await assert_settled(db, owned, other)


@pytest.mark.asyncio
async def test_revoking_the_grant_settles_the_watches_of_its_management_task(
    task_db: Fixture,
) -> None:
    db, owner, agent, thread = task_db
    grant = SimpleNamespace(id="grant-1", owner_id=owner, agent_id=agent)
    task, owned, other = await task_with_watch(
        db, owner, agent, thread, stable_id(grant.id, "account-management-task")
    )
    async with db.sessions() as session, session.begin():
        await stop_management_task(session, cast(AccountAuthorityRow, grant))
    async with db.sessions() as session:
        row = await session.get(TicketRow, task.id)
        assert row is not None and task_state(row).status == "cancelled"
    await assert_settled(db, owned, other)


@pytest.mark.asyncio
async def test_a_paused_task_keeps_its_watches(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    task, owned, _ = await task_with_watch(db, owner, agent, thread)
    async with db.sessions() as session, session.begin():
        await control_task(
            session,
            owner,
            TaskControl(task_id=task.id, action="pause", expected_version=task.version),
        )
    async with db.sessions() as session:
        watch = await session.get(MarketWatchRow, owned)
    assert watch is not None and watch.payload.get("enabled", True) is True


@pytest.mark.asyncio
async def test_a_stopped_watch_does_not_read_as_live_and_is_not_evaluated(
    task_db: Fixture, monkeypatch: pytest.MonkeyPatch
) -> None:
    db, owner, agent, thread = task_db
    state = {**LIVE, "next_check": (utcnow() + timedelta(seconds=30)).isoformat()}
    async with db.sessions() as session, session.begin():
        cancelled = MarketWatchRow(
            owner_id=owner, agent_id=agent, thread_id=thread, payload=payload(), state=state
        )
        paused = MarketWatchRow(
            owner_id=owner, agent_id=agent, thread_id=thread, payload=payload(), state=state
        )
        born_off = MarketWatchRow(
            owner_id=owner,
            agent_id=agent,
            thread_id=thread,
            payload=payload(enabled=False),
            state={},
        )
        session.add_all([cancelled, paused, born_off])
    async with db.sessions() as session, session.begin():
        await control_watch(session, owner, cancelled.id, "cancel")
        await control_watch(session, owner, paused.id, "pause", agent_id=agent)
    async with db.sessions() as session:
        for watch_id, code in ((cancelled.id, "watch_cancelled"), (paused.id, "watch_paused")):
            row = await session.get(MarketWatchRow, watch_id)
            assert row is not None and row.payload["enabled"] is False
            assert row.state["code"] == code
            assert "evaluation_status" not in row.state and "next_check" not in row.state
    assert await polled(db, monkeypatch) == set()
    # Resuming puts it back in the next poll.
    async with db.sessions() as session, session.begin():
        await control_watch(session, owner, paused.id, "resume")
    assert await polled(db, monkeypatch) == {paused.id}


@pytest.mark.asyncio
async def test_a_stopped_watch_does_not_wake_the_task_waiting_on_it(task_db: Fixture) -> None:
    db, owner, agent, thread = task_db
    task, owned, _ = await task_with_watch(db, owner, agent, thread)
    fired = utcnow().isoformat()
    async with db.sessions() as session, session.begin():
        run = await session.get(RunRow, task.payload["run_id"])
        row = await session.get(TicketRow, task.id)
        watch = await session.get(MarketWatchRow, owned)
        assert run is not None and row is not None and watch is not None
        run.status = "waiting_takeover"
        run.execution_state = {
            "environment": {
                "wait": {
                    "kind": "watch",
                    "source_id": owned,
                    "call_id": "wait-1",
                    "created_at": fired,
                }
            }
        }
        state = task_state(row)
        state.status, state.phase, state.waiting_reason = "waiting", "waiting", "external_watch"
        save_task(session, row, state)
        # The condition was met, and the owner stopped the watch before the wake was settled.
        watch.state = {**watch.state, "last_triggered": fired}
    async with db.sessions() as session, session.begin():
        await control_watch(session, owner, owned, "cancel")
    assert await resume_ready_waits(db) == 0
    async with db.sessions() as session:
        run = await session.get(RunRow, task.payload["run_id"])
        assert run is not None and run.status == "waiting_takeover"
    # The same trigger on a watch the owner resumed wakes the Task as before.
    async with db.sessions() as session, session.begin():
        await control_watch(session, owner, owned, "resume")
    assert await resume_ready_waits(db) == 1


@pytest.mark.asyncio
async def test_a_watch_that_no_longer_watches_is_not_returned_for_a_new_request(
    task_db: Fixture,
) -> None:
    """``watch_create`` returns the live watch for a repeated request. One whose
    confirmation expired is enabled and will never fire: handing it back would tell the
    Agent it has a watch when nothing is watching."""
    db, owner, agent, thread = task_db
    context = cast(ToolContext, SimpleNamespace(owner_id=owner, agent_id=agent))
    run = cast(RunRow, SimpleNamespace(model_metadata={}))
    async with db.sessions() as session, session.begin():
        keyed = MarketWatchRow(
            owner_id=owner,
            agent_id=agent,
            thread_id=thread,
            payload=(await _stored(session, owner, agent, payload(dedupe_key="eur-break"))),
            state={"lifecycle": "pending"},
        )
        plain = MarketWatchRow(
            owner_id=owner,
            agent_id=agent,
            thread_id=thread,
            payload=(await _stored(session, owner, agent, payload())),
            state={"lifecycle": "pending"},
        )
        session.add_all([keyed, plain])
    async with db.sessions() as session, session.begin():
        found = await keyed_watch(session, context, "eur-break")
        same = await identical_watch(session, context, run, thread, payload())
        assert found is not None and found.id == keyed.id
        assert same is not None and same.id == plain.id
        for row in (found, same):
            row.state = {**row.state, "lifecycle": "expired"}
    async with db.sessions() as session, session.begin():
        assert await keyed_watch(session, context, "eur-break") is None
        assert await identical_watch(session, context, run, thread, payload()) is None


async def _stored(session: Any, owner: str, agent: str, args: dict[str, Any]) -> dict[str, Any]:
    from lonora_db.market_watches import MarketWatchRepository

    return await MarketWatchRepository().stored_payload(session, owner, agent, args)
