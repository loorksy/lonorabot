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
            task_run = await session.scalar(
                select(RunRow).where(RunRow.model_metadata["task_id"].as_string() == task["id"])
            )
            assert task_run is not None
        # A Task's own sub-Task stays with the Task's work, not the conversation.
        task_context = await fixture.lease(
            {"id": task_run.id, "agent_id": agent["id"], "thread_id": task_run.thread_id}
        )
        sub_task = await call(task_context, "task_start", title="Collect the CPI print")
        async with fixture.runtime.db.sessions() as session:
            sub_ticket = await session.get(TicketRow, sub_task["id"])
            assert sub_ticket is not None
            assert sub_ticket.state["task"]["origin_thread_id"] == task_run.thread_id
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
        # The follow-up is the routine's continuation: it starts no further follow-up.
        async with fixture.runtime.db.sessions() as session:
            follow_ups = list(
                await session.scalars(
                    select(RunRow.id).where(
                        RunRow.parent_run_id == parent_id, RunRow.trigger == "follow_up"
                    )
                )
            )
            assert follow_ups == [follow_up.id]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_only_a_reporting_wakes_continuation_inherits_its_origin():
    database()
    from check_streaming import Fixture
    from lonora_contracts.domain import ThreadCreate
    from lonora_contracts.runs import RunRequest
    from lonora_db.runs import create_run
    from lonora_db.schema import RunRow
    from lonora_db.threads import create_thread, wake_origin
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Quiet review")
        peer = await fixture.agent("Quiet helper")
        conversation = await fixture.conversation(agent)
        async with fixture.runtime.db.sessions() as session, session.begin():
            work = await create_thread(
                session, fixture.owner, ThreadCreate(agent_id=agent["id"]), purpose="work"
            )
            # An activation review is told its result is not shown: its follow-up must not
            # gain a path to the conversation.
            parent = await create_run(
                session,
                fixture.owner,
                RunRequest(
                    thread_id=work.id,
                    agent_id=agent["id"],
                    trigger="activation",
                    prompt="Review",
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
                    prompt="Check",
                    parent_run_id=parent.id,
                ),
            )
            parent_id, child_id = parent.id, child.id
            assert wake_origin(parent) == {}
        await finish(fixture, parent_id, "")
        await finish(fixture, child_id, "Checked.")
        async with fixture.runtime.db.sessions() as session:
            follow_up = await session.scalar(
                select(RunRow).where(
                    RunRow.parent_run_id == parent_id, RunRow.trigger == "follow_up"
                )
            )
            assert follow_up is not None
            assert "origin_thread_id" not in follow_up.model_metadata
        await finish(fixture, follow_up.id, "Readiness looks fine.")
        assert await messages(fixture, conversation["id"]) == []
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_routines_collaboration_synthesis_reports_in_its_agents_own_conversation():
    database()
    from check_streaming import Fixture
    from lonora_contracts.collaboration import CollaborationRound, CollaborationState
    from lonora_contracts.domain import ThreadCreate
    from lonora_contracts.runs import RunRequest
    from lonora_db.collaboration import schedule_synthesis
    from lonora_db.runs import create_run
    from lonora_db.schema import CollaborationSessionRow, MessageRow, RunRow, ThreadRow
    from lonora_db.threads import create_thread
    from lonora_session.idempotency import stable_id

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Morning host")
        peer = await fixture.agent("Morning participant")
        conversation = await fixture.conversation(agent)
        async with fixture.runtime.db.sessions() as session, session.begin():
            work = await create_thread(
                session, fixture.owner, ThreadCreate(agent_id=agent["id"]), purpose="work"
            )
            host = await create_run(
                session,
                fixture.owner,
                RunRequest(
                    thread_id=work.id,
                    agent_id=agent["id"],
                    trigger="routine",
                    prompt="Ask the team",
                    metadata={"origin_thread_id": conversation["id"]},
                ),
            )
            helper = await create_thread(
                session, fixture.owner, ThreadCreate(agent_id=peer["id"]), purpose="work"
            )
            participant = await create_run(
                session,
                fixture.owner,
                RunRequest(
                    thread_id=helper.id,
                    agent_id=peer["id"],
                    trigger="peer",
                    prompt="Your view",
                    parent_run_id=host.id,
                ),
            )
            delivered = MessageRow(
                thread_id=work.id, agent_id=peer["id"], seq=1, role="assistant", content="ok"
            )
            session.add(delivered)
            await session.flush()
            collaboration = CollaborationSessionRow(
                owner_id=fixture.owner,
                agent_id=agent["id"],
                thread_id=work.id,
                payload={"subject": "Gold today"},
                state=CollaborationState(
                    rounds=[
                        CollaborationRound(
                            id="round-1",
                            request_id=host.id,
                            host_run_id=host.id,
                            subject="Gold today",
                            participant_run_ids=[participant.id],
                        )
                    ]
                ).model_dump(mode="json"),
            )
            session.add(collaboration)
            await session.flush()
            host.status = "completed"
            participant.status = "completed"
            participant.model_metadata = {
                **participant.model_metadata,
                "collaboration_session_id": collaboration.id,
                "collaboration_return_message_id": delivered.id,
            }
            await session.flush()
            thread = await session.get(ThreadRow, work.id)
            assert thread is not None
            await schedule_synthesis(session, participant, host, thread)
            synthesis_id = stable_id(collaboration.id, "synthesis:round-1")
        async with fixture.runtime.db.sessions() as session:
            synthesis = await session.get(RunRow, synthesis_id)
            assert synthesis is not None and synthesis.thread_id == work.id
            assert synthesis.model_metadata["origin_thread_id"] == conversation["id"]
        await finish(fixture, synthesis_id, "Team view: hold gold through CPI.")
        assert await messages(fixture, conversation["id"]) == ["Team view: hold gold through CPI."]
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
    from lonora_db.schema import (
        MarketWatchRow,
        MessageRow,
        RoutineRow,
        RunRow,
        ThreadPrefsRow,
        ThreadRow,
        TicketRow,
    )
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
            # The owner pinned one routine chat; a question waits in another.
            pinned = ThreadRow(owner_id=fixture.owner, agent_id=agent["id"], title="pinned")
            asking = ThreadRow(owner_id=fixture.owner, agent_id=agent["id"], title="asking")
            session.add_all([pinned, asking])
            await session.flush()
            session.add(ThreadPrefsRow(owner_id=fixture.owner, thread_id=pinned.id, pinned_order=1))
            session.add(
                RunRow(
                    thread_id=asking.id,
                    agent_id=agent["id"],
                    trigger="routine",
                    prompt="asking",
                    status="waiting_input",
                )
            )
            for name, thread in {"pinned": pinned, "asking": asking}.items():
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
            # A routine run queued by the old code, still in flight in the quiet chat.
            in_flight = RunRow(
                thread_id=quiet.id,
                agent_id=agent["id"],
                trigger="routine",
                prompt="quiet",
                model_metadata={"routine_id": routines["quiet"]},
            )
            session.add(in_flight)
            await session.flush()
            in_flight_id = in_flight.id
            # A Task's own work thread holds a watch and an in-flight follow-up: it is not
            # a routine chat, so its run is left as it is.
            session.add(
                MarketWatchRow(
                    owner_id=fixture.owner,
                    agent_id=agent["id"],
                    thread_id=task_work.id,
                    payload={"prompt": "task watch"},
                )
            )
            task_follow_up = RunRow(
                thread_id=task_work.id,
                agent_id=agent["id"],
                trigger="follow_up",
                prompt="continue",
            )
            session.add(task_follow_up)
            await session.flush()
            task_follow_up_id = task_follow_up.id
            ids = {
                "first": first.id,
                "quiet": quiet.id,
                "spoken": spoken.id,
                "tasked": tasked.id,
                "pinned": pinned.id,
                "asking": asking.id,
            }
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
                "pinned": "conversation",
                "asking": "conversation",
            }
            for name in ("first", "spoken", "tasked", "pinned", "asking"):
                routine = await session.get(RoutineRow, routines[name])
                assert routine is not None and routine.thread_id != ids[name]
                moved = await session.get(ThreadRow, routine.thread_id)
                assert moved is not None and moved.purpose == "work"
                assert moved.agent_id == agent["id"] and moved.title == name
            kept = await session.get(RoutineRow, routines["quiet"])
            assert kept is not None and kept.thread_id == ids["quiet"]
            # The in-flight run now reports to the Agent's own (earliest) conversation.
            stamped = await session.get(RunRow, in_flight_id)
            assert stamped is not None
            assert stamped.model_metadata["origin_thread_id"] == ids["first"]
            assert stamped.model_metadata["routine_id"] == routines["quiet"]
            untouched = await session.get(RunRow, task_follow_up_id)
            assert untouched is not None and "origin_thread_id" not in untouched.model_metadata
        # The moved routine's history keeps the runs from its earlier chat.
        history = await routine_history(fixture.runtime.db, routines["spoken"], fixture.owner)
        assert [run["id"] for run in history] == [earlier_id]
    finally:
        await fixture.close()
