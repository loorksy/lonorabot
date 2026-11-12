"""Routine output goes to the agent's own conversation (VISION 11.6).

A routine, and a watch set up outside any chat, works in a hidden work thread of its own
(its memory) whose origin is its Agent's own conversation. A non-empty result is copied
there; the work thread never appears in the chat list. Migration 0090 converts the
routine chats of earlier releases the same way.
"""

import importlib.util
import os
from datetime import timedelta
from pathlib import Path
from typing import Any

import pytest


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The routine output cases use the real migrated PostgreSQL schema.")


async def call(context: Any, name: str, **arguments: Any) -> dict[str, Any]:
    from uuid import uuid4

    from lonora_adapter_kit.types import ToolCall
    from lonora_tools.loader import load_tools

    return await load_tools().execute(
        ToolCall(id=name + "-" + uuid4().hex, name=name, arguments=arguments), context
    )


async def finish(fixture: Any, run_id: str, result: str) -> None:
    from lonora_agent.collaboration.outcome_return import return_outcome
    from lonora_db.schema import RunRow

    async with fixture.runtime.db.sessions() as session, session.begin():
        run = await session.get(RunRow, run_id, with_for_update=True)
        assert run is not None
        run.status, run.result = "completed", result
    await return_outcome(fixture.runtime.db, run_id)


async def messages(fixture: Any, thread_id: str) -> list[str]:
    from lonora_db.schema import MessageRow
    from sqlalchemy import select

    async with fixture.runtime.db.sessions() as session:
        return list(
            await session.scalars(
                select(MessageRow.content)
                .where(MessageRow.thread_id == thread_id)
                .order_by(MessageRow.seq)
            )
        )


@pytest.mark.asyncio
async def test_a_routine_reports_in_its_agents_own_conversation():
    database()
    from check_streaming import Fixture
    from lonora_contracts.domain import utcnow
    from lonora_db.routines import enqueue_one
    from lonora_db.schema import RoutineRow, RunRow, ThreadRow, TicketRow
    from lonora_db.threads import list_threads
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Routine reporter")
        conversation = await fixture.conversation(agent)
        routine = await fixture.request(
            "POST",
            f"/routines/{agent['id']}",
            {"prompt": "Review gold at the London open", "interval_seconds": 3600},
        )
        async with fixture.runtime.db.sessions() as session:
            thread = await session.get(ThreadRow, routine["thread_id"])
            assert thread is not None and thread.purpose == "work"
            listed = await list_threads(session, fixture.owner, agent["id"])
            assert [row.id for row in listed] == [conversation["id"]]
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RoutineRow, routine["id"], with_for_update=True)
            assert row is not None
            row.next_run_at = utcnow() - timedelta(seconds=1)
        async with fixture.runtime.db.sessions() as session, session.begin():
            assert await enqueue_one(session, routine["id"])
        async with fixture.runtime.db.sessions() as session:
            run = await session.scalar(
                select(RunRow).where(
                    RunRow.model_metadata["routine_id"].as_string() == routine["id"]
                )
            )
            assert run is not None and run.thread_id == routine["thread_id"]
            assert run.model_metadata["origin_thread_id"] == conversation["id"]
        # A Task the routine starts reports to the conversation too.
        context = await fixture.lease(
            {"id": run.id, "agent_id": agent["id"], "thread_id": run.thread_id}
        )
        task = await call(context, "task_start", title="Track the London session")
        async with fixture.runtime.db.sessions() as session:
            ticket = await session.get(TicketRow, task["id"])
            assert ticket is not None
            assert ticket.state["task"]["origin_thread_id"] == conversation["id"]
        await finish(fixture, run.id, "Gold 2,412: no setup yet, next check at 10:00.")
        assert await messages(fixture, conversation["id"]) == [
            "Gold 2,412: no setup yet, next check at 10:00."
        ]
        # The owner's chat list still shows only the Agent's own conversation.
        listed_threads = await fixture.client.get(f"/api/threads?agent_id={agent['id']}")
        assert listed_threads.is_success
        assert {row["id"] for row in listed_threads.json()} == {conversation["id"]}
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_routines_follow_up_reports_in_its_agents_own_conversation():
    database()
    from check_streaming import Fixture
    from lonora_contracts.domain import ThreadCreate
    from lonora_contracts.runs import RunRequest
    from lonora_db.runs import create_run
    from lonora_db.schema import RunRow
    from lonora_db.threads import create_thread
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Routine delegator")
        peer = await fixture.agent("Routine helper")
        conversation = await fixture.conversation(agent)
        async with fixture.runtime.db.sessions() as session, session.begin():
            work = await create_thread(
                session, fixture.owner, ThreadCreate(agent_id=agent["id"]), purpose="work"
            )
            parent = await create_run(
                session,
                fixture.owner,
                RunRequest(
                    thread_id=work.id,
                    agent_id=agent["id"],
                    trigger="routine",
                    prompt="Review gold",
                    metadata={"origin_thread_id": conversation["id"]},
                ),
            )
            helper = await create_thread(
                session, fixture.owner, ThreadCreate(agent_id=peer["id"]), purpose="work"
            )
            child = await create_run(
                session,
                fixture.owner,
                RunRequest(
                    thread_id=helper.id,
                    agent_id=peer["id"],
                    trigger="peer",
                    prompt="Read the calendar",
                    parent_run_id=parent.id,
                ),
            )
            parent_id, child_id = parent.id, child.id
        # The routine finishes first; the peer's outcome then starts its follow-up.
        await finish(fixture, parent_id, "")
        await finish(fixture, child_id, "CPI at 13:30.")
        async with fixture.runtime.db.sessions() as session:
            follow_up = await session.scalar(
                select(RunRow).where(
                    RunRow.parent_run_id == parent_id, RunRow.trigger == "follow_up"
                )
            )
            assert follow_up is not None and follow_up.thread_id == work.id
            assert follow_up.model_metadata["origin_thread_id"] == conversation["id"]
        await finish(fixture, follow_up.id, "Holding gold through CPI at 13:30.")
        assert await messages(fixture, conversation["id"]) == ["Holding gold through CPI at 13:30."]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_watch_set_outside_any_chat_reports_in_its_agents_own_conversation(
    monkeypatch: pytest.MonkeyPatch,
):
    database()
    from check_streaming import Fixture
    from lonora_db.market_watches import MarketWatchRepository
    from lonora_db.schema import ThreadRow
    from lonora_db.threads import background_origin

    async def connected(*_: Any) -> None:
        return None  # The thread is under test, not the watch's broker connection.

    monkeypatch.setattr(MarketWatchRepository, "validate_references", connected)
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Watch reporter")
        conversation = await fixture.conversation(agent)
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await MarketWatchRepository().create(
                session,
                fixture.owner,
                {
                    "account_id": "acc",
                    "symbol": "XAUUSD",
                    "condition": "above",
                    "level": "2425",
                    "prompt": "Consider adding to gold",
                },
                agent_id=agent["id"],
            )
            thread = await session.get(ThreadRow, row.thread_id)
            assert thread is not None and thread.purpose == "work"
            assert await background_origin(
                session, fixture.owner, agent["id"], row.thread_id or ""
            ) == {"origin_thread_id": conversation["id"]}
            # A watch set in a chat keeps that chat: it needs no origin.
            assert (
                await background_origin(session, fixture.owner, agent["id"], conversation["id"])
                == {}
            )
    finally:
        await fixture.close()


def migration() -> Any:
    path = (
        Path(__file__).parents[1] / "packages/db/migrations/versions/0090_routine_work_threads.py"
    )
    spec = importlib.util.spec_from_file_location("routine_work_threads", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.asyncio
async def test_migration_turns_earlier_routine_chats_into_work_threads():
    database()
    from check_streaming import Fixture
    from lonora_automation.delivery import routine_history
    from lonora_contracts.domain import utcnow
    from lonora_db.schema import MessageRow, RoutineRow, RunRow, ThreadRow, TicketRow
    from sqlalchemy import text

    module = migration()
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Migrated routines")
        async with fixture.runtime.db.sessions() as session, session.begin():
            # The routine chat of an earlier release was the Agent's first thread.
            first = ThreadRow(owner_id=fixture.owner, agent_id=agent["id"], title="first")
            session.add(first)
            await session.flush()
            quiet = ThreadRow(owner_id=fixture.owner, agent_id=agent["id"], title="quiet")
            spoken = ThreadRow(owner_id=fixture.owner, agent_id=agent["id"], title="spoken")
            session.add_all([quiet, spoken])
            await session.flush()
            session.add(
                MessageRow(thread_id=spoken.id, seq=1, role="user", content="Owner wrote here")
            )
            routines: dict[str, str] = {}
            for name, thread in {"first": first, "quiet": quiet, "spoken": spoken}.items():
                row = RoutineRow(
                    owner_id=fixture.owner,
                    agent_id=agent["id"],
                    thread_id=thread.id,
                    prompt=name,
                    interval_seconds=3600,
                    next_run_at=utcnow(),
                )
                session.add(row)
                await session.flush()
                routines[name] = row.id
            # A Task reports to this thread: it stays a conversation.
            tasked = ThreadRow(owner_id=fixture.owner, agent_id=agent["id"], title="tasked")
            task_work = ThreadRow(
                owner_id=fixture.owner, agent_id=agent["id"], title="task", purpose="work"
            )
            session.add_all([tasked, task_work])
            await session.flush()
            session.add(
                TicketRow(
                    owner_id=fixture.owner,
                    agent_id=agent["id"],
                    thread_id=task_work.id,
                    payload={"title": "task"},
                    state={"task": {"origin_thread_id": tasked.id}},
                )
            )
            row = RoutineRow(
                owner_id=fixture.owner,
                agent_id=agent["id"],
                thread_id=tasked.id,
                prompt="tasked",
                interval_seconds=3600,
                next_run_at=utcnow(),
            )
            session.add(row)
            await session.flush()
            routines["tasked"] = row.id
            earlier = RunRow(
                thread_id=spoken.id,
                agent_id=agent["id"],
                trigger="routine",
                prompt="spoken",
                model_metadata={"routine_id": routines["spoken"]},
            )
            session.add(earlier)
            await session.flush()
            earlier_id = earlier.id
            ids = {"first": first.id, "quiet": quiet.id, "spoken": spoken.id, "tasked": tasked.id}
        async with fixture.runtime.db.sessions() as session, session.begin():
            await session.execute(text(module.CONVERT))
            await session.execute(text(module.MOVE))
        async with fixture.runtime.db.sessions() as session:
            purposes = {
                name: (await session.get(ThreadRow, identifier)).purpose  # type: ignore[union-attr]
                for name, identifier in ids.items()
            }
            # The Agent's own conversation and the thread the owner wrote in stay chats.
            assert purposes == {
                "first": "conversation",
                "quiet": "work",
                "spoken": "conversation",
                "tasked": "conversation",
            }
            for name in ("first", "spoken", "tasked"):
                routine = await session.get(RoutineRow, routines[name])
                assert routine is not None and routine.thread_id != ids[name]
                moved = await session.get(ThreadRow, routine.thread_id)
                assert moved is not None and moved.purpose == "work"
                assert moved.agent_id == agent["id"] and moved.title == name
            kept = await session.get(RoutineRow, routines["quiet"])
            assert kept is not None and kept.thread_id == ids["quiet"]
        # The moved routine's history keeps the runs from its earlier chat.
        history = await routine_history(fixture.runtime.db, routines["spoken"], fixture.owner)
        assert [run["id"] for run in history] == [earlier_id]
    finally:
        await fixture.close()
