"""Silence when there is nothing (VISION 11.5).

A scheduled or background run with nothing new posts nothing. The agent decides what is
new; an empty reply posts no message, no attention item and no push, and a failed
background run leaves nothing in the conversation (no message, no preview text).
"""

import asyncio
import os
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

import pytest


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The background silence cases use the real migrated PostgreSQL schema.")


def test_who_is_background():
    from lonora_contracts.runs import WORK_TRIGGERS
    from lonora_core.run_state import BACKGROUND_TRIGGERS, is_background, may_end_silent

    for trigger in (
        "routine",
        "watch",
        "broker_event",
        "activation",
        "tickets",
        "webhook",
        "workspace_wake",
    ):
        assert is_background(trigger, {})
    # Someone waits on these: the owner, the agent that asked, or the daily brief (11.1).
    for trigger in (
        "user",
        "group",
        "owner_card",
        "agent_created",
        "peer",
        "subagent",
        "morning_brief",
        "weekly_report",
    ):
        assert not is_background(trigger, {})
    assert not is_background("follow_up", {})
    assert not is_background("follow_up", None)
    assert is_background("follow_up", {"background": True})
    assert not is_background("follow_up", {"background": "true"})
    # Background work the owner's words were given to answers them.
    assert not is_background("routine", {"owner_spoke": True})
    assert not is_background("follow_up", {"background": True, "owner_spoke": True})
    # A subagent's run owes its parent an answer; every other work trigger is background.
    assert BACKGROUND_TRIGGERS == WORK_TRIGGERS - {"subagent"}
    assert may_end_silent(True, {})
    assert not may_end_silent(True, {"owner_spoke": True})
    assert not may_end_silent(False, {})


def router(*replies: str, delta: str = "", fail: bool = False) -> tuple[Any, list[list[Any]]]:
    """A scripted model: each call takes the next reply; ``delta`` streams first.

    Like the production adapters, a reply with no text at all is a broken response unless
    the caller allowed an empty one (a background run that may end silent).
    """
    from lonora_adapter_kit.model_errors import FailureReason, ModelProviderError
    from lonora_adapter_kit.types import ModelReply
    from lonora_contracts.model_routing import ModelSelection
    from lonora_core.user_error import LonoraError

    queue = list(replies)
    requests: list[list[Any]] = []

    async def complete(
        _capability: Any,
        messages: list[Any],
        *_: Any,
        on_delta: Any = None,
        on_attempt: Any = None,
        allow_empty: bool = False,
        **__: Any,
    ) -> Any:
        requests.append(list(messages))
        selection = ModelSelection(provider="openai", model="background-silence-fixture")
        if on_attempt:
            await on_attempt(selection)
        if delta and on_delta:
            await on_delta(delta)
            # Let a live stream's coalescing publisher flush before the turn ends.
            await asyncio.sleep(0.3)
        if fail:
            raise LonoraError("scripted_provider_failure", 502)
        text = queue.pop(0) if queue else ""
        if not text and not allow_empty:
            raise ModelProviderError(FailureReason.INVALID_RESPONSE)
        return ModelReply(text=text), selection

    return complete, requests


async def execute(fixture: Any, run: Any, complete: Any, rounds: int = 4) -> None:
    from lonora_agent.executor import execute_run
    from lonora_tools.loader import load_tools

    data = {"id": run.id, "agent_id": run.agent_id, "thread_id": run.thread_id}
    context = await fixture.lease(data)
    with patch.object(context.router, "complete", complete):
        await execute_run(context, load_tools(), 120, rounds)


async def make_run(
    fixture: Any,
    agent: dict[str, Any],
    thread_id: str,
    trigger: str,
    *,
    metadata: dict[str, Any] | None = None,
    parent_run_id: str | None = None,
) -> Any:
    from lonora_contracts.runs import RunRequest
    from lonora_db.runs import create_run

    async with fixture.runtime.db.sessions() as session, session.begin():
        return await create_run(
            session,
            fixture.owner,
            RunRequest(
                thread_id=thread_id,
                agent_id=agent["id"],
                trigger=trigger,
                prompt="Review gold at the London open",
                parent_run_id=parent_run_id,
                metadata=metadata or {},
            ),
        )


async def work_thread(fixture: Any, agent: dict[str, Any]) -> str:
    from lonora_contracts.domain import ThreadCreate
    from lonora_db.threads import create_thread

    async with fixture.runtime.db.sessions() as session, session.begin():
        return (
            await create_thread(
                session, fixture.owner, ThreadCreate(agent_id=agent["id"]), purpose="work"
            )
        ).id


async def contents(fixture: Any, thread_id: str) -> list[str]:
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


async def run_events(fixture: Any, run_id: str, *kinds: str) -> list[Any]:
    from lonora_db.schema import EventRow
    from sqlalchemy import select

    async with fixture.runtime.db.sessions() as session:
        return list(
            await session.scalars(
                select(EventRow).where(EventRow.run_id == run_id, EventRow.kind.in_(kinds))
            )
        )


async def reload(fixture: Any, run_id: str) -> Any:
    from lonora_db.schema import RunRow

    async with fixture.runtime.db.sessions() as session:
        row = await session.get(RunRow, run_id)
        assert row is not None
        return row


def said(requests: list[list[Any]], text: str) -> bool:
    return any(text in str(message.content) for request in requests for message in request)


@pytest.mark.asyncio
@pytest.mark.parametrize("case", ["routine", "watch_in_chat", "broker_event", "workspace_wake"])
async def test_an_empty_background_reply_posts_nothing(case: str):
    database()
    from check_streaming import Fixture
    from lonora_agent.context.routine import BACKGROUND
    from lonora_agent.runtime_notices import NO_ANSWER
    from lonora_contracts.broker_activity import BrokerActivity
    from lonora_contracts.domain import utcnow
    from lonora_db.personal_agent import ensure_personal_agent
    from lonora_db.schema import AgentRow, AttentionRow, EventRow, RunRow
    from lonora_db.threads import conversation_thread
    from lonora_db.workspace_wakes import wake_by_handle
    from lonora_gateway.attention import attention_tick
    from lonora_trading.broker_recovery import wake_for_activity
    from sqlalchemy import select
    from test_proactive_wakes import position, retire, simulation

    fixture = await Fixture().open()
    connection = ""
    try:
        agent = await fixture.agent("Quiet desk")
        conversation = (await fixture.conversation(agent))["id"]
        if case == "routine":
            work = await work_thread(fixture, agent)
            run = await make_run(
                fixture, agent, work, "routine", metadata={"origin_thread_id": conversation}
            )
        elif case == "watch_in_chat":
            run = await make_run(fixture, agent, conversation, "watch")
        elif case == "workspace_wake":
            async with fixture.runtime.db.sessions() as session, session.begin():
                caller = await session.get(AgentRow, agent["id"])
                assert caller is not None
                run = await wake_by_handle(session, caller, "@" + caller.name, "build finished")
        else:
            connection = await simulation(fixture)
            async with fixture.runtime.db.sessions() as session, session.begin():
                personal = await ensure_personal_agent(session, fixture.owner)
                personal.paused = False
                agent = {"id": personal.id}
                conversation = (await conversation_thread(session, fixture.owner, personal.id)).id
                change = BrokerActivity(
                    id=str(uuid4()),
                    account_id=connection,
                    symbol="XAUUSD",
                    ticket="T-" + uuid4().hex[:8],
                    resource="position",
                    change="closed",
                    origin="external",
                    observed_at=utcnow(),
                    previous=position("T-quiet"),
                )
                await wake_for_activity(session, fixture.owner, connection, 7, [change])
            async with fixture.runtime.db.sessions() as session:
                run = await session.scalar(
                    select(RunRow).where(
                        RunRow.trigger == "broker_event",
                        RunRow.model_metadata["account_id"].as_string() == connection,
                    )
                )
                assert run is not None
                event = await session.scalar(
                    select(EventRow).where(
                        EventRow.kind == "broker.external_activity",
                        EventRow.payload["id"].as_string() == change.id,
                    )
                )
                assert event is not None and event.payload["wakes_agent"] is True
        before_chat = await contents(fixture, conversation)
        before_work = await contents(fixture, run.thread_id)
        complete, requests = router("")
        await execute(fixture, run, complete)
        row = await reload(fixture, run.id)
        assert row.status == "completed", (row.status, row.error_code)
        assert row.result == ""
        assert row.model_metadata["reply_outcome"] == "silent"
        # Asked once, told its reply may be empty, and never nudged for an answer.
        assert len(requests) == 1
        assert said(requests, BACKGROUND)
        assert not said(requests, NO_ANSWER)
        assert await contents(fixture, conversation) == before_chat
        assert await contents(fixture, run.thread_id) == before_work
        assert not await run_events(
            fixture, run.id, "message.created", "run.delta", "run.rich_partial"
        )
        # No attention item stands in for the reply.
        await attention_tick(
            fixture.runtime.db, fixture.runtime.services(fixture.owner).brokers, fixture.owner
        )
        async with fixture.runtime.db.sessions() as session:
            items = list(
                await session.scalars(
                    select(AttentionRow.code).where(
                        AttentionRow.owner_id == fixture.owner,
                        AttentionRow.agent_id == agent["id"],
                        AttentionRow.status.in_(["pending", "ready"]),
                    )
                )
            )
        assert items == []
    finally:
        if connection:
            await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_background_run_at_its_limit_posts_no_fallback():
    database()
    from check_streaming import Fixture
    from lonora_agent.runtime_notices import BACKGROUND_FINISH

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Limited desk")
        conversation = (await fixture.conversation(agent))["id"]
        work = await work_thread(fixture, agent)
        run = await make_run(
            fixture, agent, work, "routine", metadata={"origin_thread_id": conversation}
        )
        complete, requests = router("")
        await execute(fixture, run, complete, rounds=1)
        row = await reload(fixture, run.id)
        assert row.status == "completed", (row.status, row.error_code)
        assert row.result == ""
        assert row.model_metadata["reply_outcome"] == "limited"
        assert len(requests) == 1
        notices = [
            str(message.content)
            for message in requests[0]
            if "No tool call will execute any more" in str(message.content)
        ]
        assert len(notices) == 1
        assert ("Do not invent progress." + BACKGROUND_FINISH + '"}') in notices[0]
        assert await contents(fixture, conversation) == []
        assert await contents(fixture, work) == []
        stored = cast(list[dict[str, Any]], row.execution_state["messages"])
        assert not [m for m in stored if m["role"] == "assistant" and not m["content"].strip()]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_failed_background_run_leaves_nothing_in_the_conversation():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Failing desk")
        conversation = (await fixture.conversation(agent))["id"]
        # A watch set in the chat runs in the chat: its half-written reply is never shown.
        watch = await make_run(fixture, agent, conversation, "watch")
        complete, _ = router(delta="Gold broke 2,400.\n\nChecking the London open.\n\n", fail=True)
        await execute(fixture, watch, complete)
        row = await reload(fixture, watch.id)
        assert row.status == "failed"
        assert not await run_events(fixture, watch.id, "run.delta", "run.rich_partial")
        listed = cast(
            list[dict[str, Any]], await fixture.request("GET", f"/runs?thread_id={conversation}")
        )
        failed = next(item for item in listed if item["id"] == watch.id)
        assert failed["background"] is True
        stream = cast(dict[str, Any], failed["stream"] or {})
        assert stream.get("text", "") == ""
        assert await contents(fixture, conversation) == []
        # A routine that fails in its work thread copies nothing to the conversation.
        work = await work_thread(fixture, agent)
        routine = await make_run(
            fixture, agent, work, "routine", metadata={"origin_thread_id": conversation}
        )
        await execute(fixture, routine, complete)
        assert (await reload(fixture, routine.id)).status == "failed"
        assert await contents(fixture, conversation) == []
        # An owner's own failed request still shows: it is not background.
        user = await fixture.run(agent, {"id": conversation})
        assert user["background"] is False
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_background_reply_with_news_is_posted_whole_without_a_preview():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Reporting desk")
        conversation = (await fixture.conversation(agent))["id"]
        news = "Gold broke 2,400.\n\nThe London open confirmed the setup."
        watch = await make_run(fixture, agent, conversation, "watch")
        complete, _ = router(news, delta=news)
        await execute(fixture, watch, complete)
        row = await reload(fixture, watch.id)
        assert row.status == "completed" and row.result == news
        assert await contents(fixture, conversation) == [news]
        assert not await run_events(fixture, watch.id, "run.delta", "run.rich_partial")
        # The owner's own request still streams its preview.
        asked = await fixture.run(agent, {"id": conversation})
        user_run = await reload(fixture, asked["id"])
        complete, _ = router("Gold is at 2,401.", delta="Gold is at 2,401.")
        await execute(fixture, user_run, complete)
        assert await run_events(fixture, user_run.id, "run.delta")
    finally:
        await fixture.close()


async def returned_helper(
    fixture: Any, agent: dict[str, Any], parent: Any, status: str, result: str | None
) -> Any:
    """A subagent of ``parent`` that ended with ``status`` and ``result``, returned."""
    from lonora_agent.collaboration.outcome_return import return_outcome
    from lonora_db.schema import RunRow

    helper_thread = await work_thread(fixture, agent)
    child = await make_run(fixture, agent, helper_thread, "subagent", parent_run_id=parent.id)
    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(RunRow, child.id, with_for_update=True)
        assert row is not None
        row.status, row.result = status, result
    await return_outcome(fixture.runtime.db, child.id)
    return child


async def steered_text(fixture: Any, run_id: str) -> str:
    """What reaches ``run_id`` by steering, and the purpose of the threads it is in."""
    from lonora_db.schema import MessageRow, SteeringRow, ThreadRow
    from sqlalchemy import select

    async with fixture.runtime.db.sessions() as session:
        rows = list(
            await session.execute(
                select(MessageRow.content, ThreadRow.purpose)
                .join(SteeringRow, SteeringRow.message_id == MessageRow.id)
                .join(ThreadRow, ThreadRow.id == MessageRow.thread_id)
                .where(SteeringRow.run_id == run_id)
            )
        )
    assert all(purpose == "work" for _, purpose in rows), rows
    return "\n".join(content for content, _ in rows)


async def follow_ups(fixture: Any, parent_id: str) -> list[Any]:
    from lonora_db.schema import RunRow
    from sqlalchemy import select

    async with fixture.runtime.db.sessions() as session:
        return list(
            await session.scalars(
                select(RunRow).where(
                    RunRow.parent_run_id == parent_id, RunRow.trigger == "follow_up"
                )
            )
        )


async def ended(fixture: Any, run: Any, status: str = "completed", result: str = "") -> None:
    from lonora_db.schema import RunRow

    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(RunRow, run.id, with_for_update=True)
        assert row is not None
        row.status, row.result = status, result


@pytest.mark.asyncio
async def test_a_follow_up_is_background_when_its_parent_is():
    database()
    from check_streaming import Fixture
    from lonora_agent.runtime_notices import NO_ANSWER

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Follow-up desk")
        conversation = (await fixture.conversation(agent))["id"]
        work = await work_thread(fixture, agent)
        routine = await make_run(
            fixture, agent, work, "routine", metadata={"origin_thread_id": conversation}
        )
        await ended(fixture, routine)
        await returned_helper(fixture, agent, routine, "completed", "CPI printed 3.1%.")
        [follow_up] = await follow_ups(fixture, routine.id)
        assert follow_up.model_metadata["background"] is True
        assert follow_up.prompt.startswith("Use the returned peer outcome to finish the background")
        complete, requests = router("")
        await execute(fixture, follow_up, complete)
        row = await reload(fixture, follow_up.id)
        assert row.status == "completed" and row.result == ""
        assert len(requests) == 1 and not said(requests, NO_ANSWER)
        assert await contents(fixture, conversation) == []
        # A follow-up of the owner's own request answers the owner.
        asked = await fixture.run(agent, {"id": conversation})
        user_run = await reload(fixture, asked["id"])
        await ended(fixture, user_run, result="Asked a helper.")
        await returned_helper(fixture, agent, user_run, "completed", "CPI printed 3.1%.")
        [answer] = await follow_ups(fixture, user_run.id)
        assert "background" not in answer.model_metadata
        assert answer.prompt == "Use the returned peer outcome to complete the owner's request."
        # An owner run is never offered an empty reply; a blank one is nudged for an answer.
        complete, requests = router(" ", "CPI came in at 3.1%.")
        await execute(fixture, answer, complete)
        assert len(requests) == 2 and said(requests[1:], NO_ANSWER)
        assert (await reload(fixture, answer.id)).result == "CPI came in at 3.1%."
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_the_background_mark_is_set_only_by_the_server():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Marked desk")
        conversation = await fixture.conversation(agent)
        for trigger in ("user", "follow_up"):
            created = await fixture.request(
                "POST",
                "/runs",
                {
                    "agent_id": agent["id"],
                    "thread_id": conversation["id"],
                    "trigger": trigger,
                    "metadata": {"background": True},
                },
            )
            assert created["background"] is False
            async with fixture.runtime.db.sessions() as session:
                row = await session.get(RunRow, created["id"])
                assert row is not None and "background" not in row.model_metadata
            await ended(fixture, row, status="cancelled")
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_the_owner_writing_to_a_background_run_ends_its_silence():
    database()
    from check_streaming import Fixture
    from lonora_agent.runtime_notices import NO_ANSWER
    from lonora_db.schema import RunRow
    from lonora_tools.runtime_control import silence
    from test_background_questions import QUESTION, ask, background_run, send

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Answering desk")
        conversation = await fixture.conversation(agent)
        run = await background_run(fixture, agent, conversation)
        question = (await ask(fixture, run))["input_request"]
        status, _ = await send(
            fixture, conversation["id"], "أبقِها", reply_to=question["message_id"]
        )
        assert status < 300
        # Once the owner has spoken the run is not offered an empty reply; a blank one is
        # nudged for an answer.
        complete, requests = router(" ", "أبقيت الصفقة.")
        row = await reload(fixture, run["id"])
        await execute(fixture, row, complete)
        assert len(requests) == 2 and said(requests[1:], NO_ANSWER)
        row = await reload(fixture, run["id"])
        assert row.status == "completed" and row.execution_state["owner_spoke"] is True
        # The owner is waiting on this answer, so it streams like an owner turn.
        assert await run_events(fixture, run["id"], "run.delta")
        assert await contents(fixture, conversation["id"]) == [
            QUESTION,
            "أبقِها",
            "أبقيت الصفقة.",
        ]
        # And the silence tool now refuses it: the owner is waiting on an answer.
        again = await make_run(
            fixture,
            agent,
            row.thread_id,
            "routine",
            metadata={"origin_thread_id": conversation["id"]},
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            spoken = await session.get(RunRow, again.id, with_for_update=True)
            assert spoken is not None
            spoken.execution_state = {"owner_spoke": True}
        context = await fixture.lease(
            {"id": again.id, "agent_id": again.agent_id, "thread_id": again.thread_id}
        )
        refused = await silence(context, {})
        assert refused["ok"] is False
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_group_silence_accepts_a_background_wake():
    database()
    from check_streaming import Fixture
    from lonora_tools.runtime_control import silence

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Silent desk")
        conversation = (await fixture.conversation(agent))["id"]
        work = await work_thread(fixture, agent)
        for trigger, thread in (("broker_event", work), ("workspace_wake", conversation)):
            run = await make_run(fixture, agent, thread, trigger)
            context = await fixture.lease(
                {"id": run.id, "agent_id": run.agent_id, "thread_id": run.thread_id}
            )
            assert await silence(context, {}) == {"_runtime_silence": True}
            await ended(fixture, run, status="cancelled")
        # The owner's own message in a direct chat is always answered.
        user = await fixture.run(agent, {"id": conversation})
        refused = await silence(await fixture.lease(user), {})
        assert refused["code"] == "silence_requires_group"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_an_empty_or_failed_helper_of_ended_background_work_posts_no_card():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Helper desk")
        conversation = (await fixture.conversation(agent))["id"]
        # A watch set in the chat has ended; its helper failed: nothing reaches the chat.
        watch = await make_run(fixture, agent, conversation, "watch")
        await ended(fixture, watch)
        await returned_helper(fixture, agent, watch, "failed", None)
        await returned_helper(fixture, agent, watch, "completed", "")
        assert await contents(fixture, conversation) == []
        assert await follow_ups(fixture, watch.id) == []
        # A helper that brought something back reaches the work, not the chat: its
        # background follow-up reads it and decides whether anything is new.
        helped = await returned_helper(fixture, agent, watch, "completed", "Gold held 2,400.")
        assert await contents(fixture, conversation) == []
        [follow_up] = await follow_ups(fixture, watch.id)
        assert follow_up.model_metadata["background"] is True
        assert helped.id in await steered_text(fixture, follow_up.id)
        # A watch still running is still told its helper failed (it may wait for it), out
        # of the owner's sight.
        running = await make_run(fixture, agent, conversation, "watch")
        failed = await returned_helper(fixture, agent, running, "failed", None)
        assert await contents(fixture, conversation) == []
        assert failed.id in await steered_text(fixture, running.id)
        # In a work thread every outcome stays: it is the work's memory.
        work = await work_thread(fixture, agent)
        routine = await make_run(
            fixture, agent, work, "routine", metadata={"origin_thread_id": conversation}
        )
        await ended(fixture, routine)
        lost = await returned_helper(fixture, agent, routine, "failed", None)
        assert any(lost.id in text for text in await contents(fixture, work))
        assert len(await follow_ups(fixture, routine.id)) == 1
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_work_thread_message_is_never_sent_to_a_channel():
    database()
    from check_streaming import Fixture
    from lonora_adapters.channels.webhook import WebhookAdapter
    from lonora_agent.collaboration.outcome_return import return_outcome
    from lonora_db.schema import IntegrationRow
    from lonora_gateway.event_dispatch import dispatch_channels

    fixture = await Fixture().open()
    channel_id = ""
    try:
        agent = await fixture.agent("Channel desk")
        conversation = (await fixture.conversation(agent))["id"]
        services = fixture.runtime.services(fixture.owner)
        secret_id = await services.secrets.write("silence-scripted", uuid4().hex, "integration")
        async with fixture.runtime.db.sessions() as session, session.begin():
            channel = IntegrationRow(
                owner_id=fixture.owner,
                payload={
                    "enabled": True,
                    "type": "webhook",
                    "url": "https://example.test/silence",
                    "secret_id": secret_id,
                },
            )
            session.add(channel)
            await session.flush()
            channel_id = channel.id
        sent: list[str] = []

        async def scripted_send(_adapter: WebhookAdapter, destination: str, content: str):
            sent.append(content)
            return {"status": "fixture-confirmed"}

        with patch("lonora_gateway.event_dispatch.WebhookAdapter.send", scripted_send):
            # Skip whatever the owner's earlier fixtures left in the event log.
            await dispatch_channels(fixture.runtime.db, services)
            sent.clear()
            work = await work_thread(fixture, agent)
            routine = await make_run(
                fixture, agent, work, "routine", metadata={"origin_thread_id": conversation}
            )
            await ended(fixture, routine)
            await returned_helper(fixture, agent, routine, "failed", None)
            assert await contents(fixture, work)
            report = await make_run(
                fixture, agent, work, "routine", metadata={"origin_thread_id": conversation}
            )
            await ended(fixture, report, result="Gold 2,412: no setup yet.")
            await return_outcome(fixture.runtime.db, report.id)
            await dispatch_channels(fixture.runtime.db, services)
        assert sent == ["Gold 2,412: no setup yet."]
    finally:
        if channel_id:
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(IntegrationRow, channel_id)
                if row is not None:
                    await session.delete(row)
        await fixture.close()


@pytest.mark.asyncio
async def test_wake_sources_raise_an_item_only_when_no_run_speaks():
    database()
    from check_streaming import Fixture
    from lonora_contracts.broker_activity import BrokerActivity
    from lonora_contracts.domain import ThreadCreate, utcnow
    from lonora_db.personal_agent import ensure_personal_agent
    from lonora_db.schema import AgentRow, AttentionRow, EventRow, RunRow, TradingOpportunityRow
    from lonora_db.threads import create_thread
    from lonora_gateway.attention import attention_tick
    from lonora_trading.broker_recovery import wake_for_activity
    from lonora_trading.opportunities import wake_reports
    from sqlalchemy import select
    from test_proactive_wakes import position, retire, simulation

    fixture = await Fixture().open()
    connection = ""

    def activity() -> Any:
        ticket = "T-" + uuid4().hex[:8]
        return BrokerActivity(
            id=str(uuid4()),
            account_id=connection,
            symbol="XAUUSD",
            ticket=ticket,
            resource="position",
            change="closed",
            origin="external",
            observed_at=utcnow(),
            previous=position(ticket),
        )

    async def items(code: str) -> list[Any]:
        await attention_tick(
            fixture.runtime.db, fixture.runtime.services(fixture.owner).brokers, fixture.owner
        )
        async with fixture.runtime.db.sessions() as session:
            return list(
                await session.scalars(
                    select(AttentionRow).where(
                        AttentionRow.owner_id == fixture.owner,
                        AttentionRow.code == code,
                        AttentionRow.status.in_(["pending", "ready"]),
                    )
                )
            )

    try:
        connection = await simulation(fixture)
        # Lonora is woken by the owner's own broker activity: its reply is the news.
        async with fixture.runtime.db.sessions() as session, session.begin():
            personal = await ensure_personal_agent(session, fixture.owner)
            personal.paused = False
            personal_id = personal.id
            await wake_for_activity(session, fixture.owner, connection, 1, [activity()])
        assert await items("external_broker_activity") == []
        # While Lonora is paused nothing is woken, so the item is the owner's only signal.
        async with fixture.runtime.db.sessions() as session, session.begin():
            personal = await session.get(AgentRow, personal_id, with_for_update=True)
            assert personal is not None
            personal.paused = True
            await wake_for_activity(session, fixture.owner, connection, 2, [activity()])
            personal.paused = False
        [unseen] = await items("external_broker_activity")
        # A later change that wakes Lonora withdraws no item about another change.
        async with fixture.runtime.db.sessions() as session, session.begin():
            await wake_for_activity(session, fixture.owner, connection, 3, [activity()])
        assert [item.id for item in await items("external_broker_activity")] == [unseen.id]
        # If that woken run fails, the change it stood for returns as the owner's item.
        async with fixture.runtime.db.sessions() as session:
            woken = await session.scalar(
                select(RunRow)
                .where(
                    RunRow.trigger == "broker_event",
                    RunRow.model_metadata["broker_revision"].as_integer() == 3,
                )
                .order_by(RunRow.created_at.desc())
            )
            assert woken is not None
        complete, _ = router(fail=True)
        await execute(fixture, woken, complete)
        assert (await reload(fixture, woken.id)).status == "failed"
        async with fixture.runtime.db.sessions() as session:
            failure = await session.scalar(
                select(EventRow).where(EventRow.kind == "run.failed", EventRow.run_id == woken.id)
            )
            assert failure is not None
        returned = await items("external_broker_activity")
        assert any(failure.cursor in item.source_events for item in returned), [
            item.source_events for item in returned
        ]
        # An opportunity's wake reports only in its agent's own conversation.
        agent = await fixture.agent("Opportunity desk")
        conversation = (await fixture.conversation(agent))["id"]
        async with fixture.runtime.db.sessions() as session, session.begin():
            work = await create_thread(
                session, fixture.owner, ThreadCreate(agent_id=agent["id"]), purpose="work"
            )
            here = TradingOpportunityRow(agent_id=agent["id"], thread_id=conversation)
            elsewhere = TradingOpportunityRow(agent_id=agent["id"], thread_id=work.id)
            assert await wake_reports(session, here)
            assert not await wake_reports(session, elsewhere)
            row = await session.get(AgentRow, agent["id"], with_for_update=True)
            assert row is not None
            row.paused = True
            assert not await wake_reports(session, here)
            row.paused = False
    finally:
        if connection:
            await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_task_completed_empty_is_not_news():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import EventRow, TicketRow
    from lonora_db.tasks import save_task, task_state
    from sqlalchemy import select
    from test_routine_output import call

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Task desk")
        conversation = await fixture.conversation(agent)
        run = await fixture.run(agent, conversation)
        context = await fixture.lease(run)
        task = await call(context, "task_start", title="Track the London session")
        for result in ("", "Closed at 2,410."):
            async with fixture.runtime.db.sessions() as session, session.begin():
                ticket = await session.get(TicketRow, task["id"], with_for_update=True)
                assert ticket is not None
                ticket.state = {**ticket.state, "result": result}
                state = task_state(ticket)
                state.status = "completed"
                save_task(session, ticket, state)
            async with fixture.runtime.db.sessions() as session:
                event = await session.scalar(
                    select(EventRow)
                    .where(
                        EventRow.kind == "task.updated",
                        EventRow.payload["id"].as_string() == task["id"],
                    )
                    .order_by(EventRow.cursor.desc())
                )
                assert event is not None
                assert event.payload["result_empty"] is (result == "")
    finally:
        await fixture.close()


def empty_stop(provider: str, stream: bool, stop: str) -> Any:
    """A provider response that ended with ``stop`` and carries no text and no call."""
    import json

    import httpx

    def sse(*events: dict[str, Any], done: bool = False) -> str:
        body = "".join("data: " + json.dumps(event) + "\n\n" for event in events)
        return body + ("data: [DONE]\n\n" if done else "")

    def handle(_: httpx.Request) -> httpx.Response:
        if provider == "anthropic" and stream:
            return httpx.Response(
                200,
                text=sse(
                    {"type": "message_start", "message": {"id": "m", "usage": {}}},
                    {"type": "message_delta", "delta": {"stop_reason": stop}, "usage": {}},
                    {"type": "message_stop"},
                ),
            )
        if provider == "anthropic":
            return httpx.Response(
                200, json={"id": "m", "content": [], "stop_reason": stop, "usage": {}}
            )
        if stream:
            return httpx.Response(
                200,
                text=sse({"id": "c", "choices": [{"delta": {}, "finish_reason": stop}]}, done=True),
            )
        return httpx.Response(
            200,
            json={
                "id": "c",
                "choices": [{"message": {"content": None}, "finish_reason": stop}],
                "usage": {},
            },
        )

    return handle


async def adapter_complete(provider: str, stream: bool, stop: str, **options: Any) -> Any:
    import httpx
    from lonora_adapter_kit.types import ModelMessage
    from lonora_adapters.models.anthropic import AnthropicAdapter
    from lonora_adapters.models.openai import OpenAIAdapter

    adapter_type: Any = AnthropicAdapter if provider == "anthropic" else OpenAIAdapter

    async def delta(_: str) -> None:
        return None

    async with httpx.AsyncClient(
        transport=httpx.MockTransport(empty_stop(provider, stream, stop))
    ) as client:
        adapter = adapter_type("fixture-key", client)
        return await adapter.complete(
            "fixture-model",
            [ModelMessage(role="user", content="Anything new on gold?")],
            [],
            on_delta=delta if stream else None,
            **options,
        )


@pytest.mark.asyncio
@pytest.mark.parametrize("provider", ["anthropic", "openai"])
@pytest.mark.parametrize("stream", [False, True])
async def test_an_empty_normal_stop_is_a_reply_only_where_silence_is_allowed(
    provider: str, stream: bool
):
    from lonora_adapter_kit.model_errors import FailureReason, ModelProviderError

    normal = "end_turn" if provider == "anthropic" else "stop"
    cut = "max_tokens" if provider == "anthropic" else "length"
    reply = await adapter_complete(provider, stream, normal, allow_empty=True)
    assert reply.text == "" and reply.tool_calls == []
    # Elsewhere an empty reply is still a broken response the router retries and falls back on.
    with pytest.raises(ModelProviderError) as broken:
        await adapter_complete(provider, stream, normal)
    assert broken.value.reason is FailureReason.INVALID_RESPONSE
    # A reply cut off at its output limit is never silence.
    with pytest.raises(ModelProviderError) as truncated:
        await adapter_complete(provider, stream, cut, allow_empty=True)
    assert truncated.value.reason is FailureReason.TRUNCATED
    # Nor is a turn that ended for calls it does not carry, or a gateway's error finish.
    for odd in ("tool_use", "tool_calls", "error"):
        with pytest.raises(ModelProviderError) as malformed:
            await adapter_complete(provider, stream, odd, allow_empty=True)
        assert malformed.value.reason is FailureReason.INVALID_RESPONSE


UNVERIFIED_EN = (
    "The broker acknowledged the request, but its resulting state is not yet independently "
    "verified. I will not resend it."
)


def seeded_trade(words: str) -> dict[str, Any]:
    """A checkpoint whose pending order the broker confirms without verification."""
    from lonora_adapter_kit.types import ModelMessage, ToolCall

    buy = ToolCall(id="buy", name="trade_execute", arguments={"action": "buy", "symbol": "XAUUSD"})
    messages = [
        ModelMessage(role="user", content=words),
        ModelMessage(role="assistant", content="", tool_calls=[buy]),
    ]
    return {
        "messages": [item.model_dump(mode="json") for item in messages],
        "pending": [buy.model_dump(mode="json")],
        "instruction_skill_ids": [],
        "rounds": 1,
        "environment": {"version": 1},
    }


def trade_and_silence() -> Any:
    from lonora_tools.base import Tool
    from lonora_tools.registry import ToolRegistry
    from lonora_tools.runtime_control import tools as control_tools
    from pydantic import BaseModel

    class Anything(BaseModel):
        model_config = {"extra": "allow"}

    async def unverified(context: Any, _: dict[str, Any]) -> dict[str, Any]:
        return {
            "operation_id": "op-" + context.call_id,
            "status": "confirmed",
            "details": {"verification": {"status": "pending"}},
        }

    silence = next(tool for tool in control_tools() if tool.name == "group_silence")
    return ToolRegistry(
        [Tool("trade_execute", "Trade", Anything, unverified, financial=True), silence]
    )


async def seeded_run(fixture: Any, trigger: str, state: dict[str, Any]) -> Any:
    from lonora_db.schema import RunRow

    agent = await fixture.agent("Trading desk")
    conversation = (await fixture.conversation(agent))["id"]
    work = await work_thread(fixture, agent)
    run = await make_run(fixture, agent, work, trigger, metadata={"origin_thread_id": conversation})
    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(RunRow, run.id, with_for_update=True)
        assert row is not None
        row.execution_state = state
    return run, conversation


@pytest.mark.asyncio
async def test_a_silent_exit_still_reports_an_unverified_order():
    database()
    from check_streaming import Fixture
    from lonora_adapter_kit.types import ModelReply, ToolCall
    from lonora_agent.executor import execute_run
    from lonora_contracts.model_routing import ModelSelection

    fixture = await Fixture().open()
    try:
        run, conversation = await seeded_run(
            fixture, "broker_event", seeded_trade("Broker activity on the gold position.")
        )

        async def complete(*_: Any, **__: Any) -> Any:
            silent = ToolCall(id="quiet-" + uuid4().hex, name="group_silence", arguments={})
            return ModelReply(tool_calls=[silent]), ModelSelection(
                provider="openai", model="background-silence-fixture"
            )

        context = await fixture.lease(
            {"id": run.id, "agent_id": run.agent_id, "thread_id": run.thread_id}
        )
        with patch.object(context.router, "complete", complete):
            await execute_run(context, trade_and_silence(), 120, 6)
        row = await reload(fixture, run.id)
        # 5.3.3 and 6.4: an order the broker confirmed but nothing verified is always news.
        assert row.status == "completed" and row.result == UNVERIFIED_EN, row.result
        assert await contents(fixture, conversation) == [UNVERIFIED_EN]
    finally:
        await fixture.close()


@pytest.mark.asyncio
@pytest.mark.parametrize("final", ["failed", "calls_only"])
async def test_at_the_limit_only_the_model_chooses_silence(final: str):
    database()
    from check_streaming import Fixture
    from lonora_adapter_kit.types import ModelReply, ToolCall
    from lonora_agent.executor import execute_run
    from lonora_contracts.model_routing import ModelSelection
    from lonora_core.user_error import LonoraError

    fixture = await Fixture().open()
    try:
        run, _ = await seeded_run(
            fixture, "routine", seeded_trade("Review the gold position at the London open.")
        )

        async def complete(*_: Any, **__: Any) -> Any:
            if final == "failed":
                raise LonoraError("scripted_provider_failure", 502)
            stray = ToolCall(id="stray-" + uuid4().hex, name="trade_execute", arguments={})
            return ModelReply(tool_calls=[stray]), ModelSelection(
                provider="openai", model="background-silence-fixture"
            )

        context = await fixture.lease(
            {"id": run.id, "agent_id": run.agent_id, "thread_id": run.thread_id}
        )
        with patch.object(context.router, "complete", complete):
            await execute_run(context, trade_and_silence(), 120, 2)
        row = await reload(fixture, run.id)
        assert row.model_metadata["exit_reason"] == "tool_round_limit"
        # The model never chose silence; the order nothing verified is the report (5.3.3).
        assert row.result == UNVERIFIED_EN, row.result
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_an_owner_message_taken_by_background_work_is_answered():
    database()
    from check_streaming import Fixture
    from lonora_agent.runtime_notices import NO_ANSWER
    from test_background_questions import send

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Busy desk")
        conversation = (await fixture.conversation(agent))["id"]
        # A watch set in the chat ended; its helper's result queued a background follow-up.
        watch = await make_run(fixture, agent, conversation, "watch")
        await ended(fixture, watch)
        await returned_helper(fixture, agent, watch, "completed", "Gold held 2,400.")
        [follow_up] = await follow_ups(fixture, watch.id)
        status, body = await send(fixture, conversation, "And silver?")
        assert status < 300, body
        # The follow-up takes the owner's words (they can still steer it) ...
        assert body["run_ids"] == [follow_up.id]
        # ... and from then on it answers them: no silence, and it streams.
        complete, requests = router(" ", "Silver is at 31.")
        await execute(fixture, follow_up, complete)
        assert len(requests) == 2 and said(requests[1:], NO_ANSWER)
        row = await reload(fixture, follow_up.id)
        assert row.result == "Silver is at 31." and row.model_metadata["owner_spoke"] is True
        assert "Silver is at 31." in await contents(fixture, conversation)
        listed = await fixture.request("GET", "/runs/" + follow_up.id)
        assert listed["background"] is False
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_an_empty_background_turn_is_never_sent_back_to_the_model():
    database()
    from check_streaming import Fixture
    from lonora_adapter_kit.types import ModelReply
    from lonora_contracts.model_routing import ModelSelection
    from lonora_db.schema import MessageRow, SteeringRow, ThreadRow

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Steered desk")
        conversation = (await fixture.conversation(agent))["id"]
        work = await work_thread(fixture, agent)
        run = await make_run(
            fixture, agent, work, "routine", metadata={"origin_thread_id": conversation}
        )
        sent: list[list[Any]] = []

        async def complete(_capability: Any, messages: list[Any], *_: Any, **__: Any) -> Any:
            sent.append(list(messages))
            selection = ModelSelection(provider="openai", model="background-silence-fixture")
            if len(sent) > 1:
                return ModelReply(text="Gold held 2,400."), selection
            # A helper's outcome arrives while this turn runs.
            async with fixture.runtime.db.sessions() as session, session.begin():
                thread = await session.get(ThreadRow, work, with_for_update=True)
                assert thread is not None
                outcome = MessageRow(
                    thread_id=work,
                    agent_id=agent["id"],
                    role="assistant",
                    seq=thread.next_seq,
                    content="<peer_outcome run_id='helper' status='completed'>\n"
                    "Gold held 2,400.\n</peer_outcome>",
                )
                thread.next_seq += 1
                session.add(outcome)
                await session.flush()
                session.add(SteeringRow(run_id=run.id, message_id=outcome.id))
            return ModelReply(text=""), selection

        await execute(fixture, run, complete)
        assert len(sent) == 2
        blank = [
            message
            for message in sent[1]
            if message.role == "assistant"
            and not message.content.strip()
            and not message.tool_calls
        ]
        assert blank == []
        assert (await reload(fixture, run.id)).result == "Gold held 2,400."
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_failed_background_run_gets_no_helper_card_in_the_chat():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Failed desk")
        conversation = (await fixture.conversation(agent))["id"]
        for status in ("failed", "cancelled"):
            watch = await make_run(fixture, agent, conversation, "watch")
            await ended(fixture, watch, status=status)
            await returned_helper(fixture, agent, watch, "completed", "Gold held 2,400.")
            assert await follow_ups(fixture, watch.id) == []
        # Nothing acts on a helper's result once its background work failed: no card.
        assert await contents(fixture, conversation) == []
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_subagent_of_background_work_works_in_a_hidden_thread():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow, ThreadRow
    from lonora_db.threads import list_threads, report_thread
    from test_routine_output import call

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Delegating desk")
        conversation = (await fixture.conversation(agent))["id"]
        work = await work_thread(fixture, agent)
        routine = await make_run(
            fixture, agent, work, "routine", metadata={"origin_thread_id": conversation}
        )
        context = await fixture.lease(
            {"id": routine.id, "agent_id": routine.agent_id, "thread_id": routine.thread_id}
        )
        spawned = await call(context, "subagent_spawn", task="Check today's calendar")
        async with fixture.runtime.db.sessions() as session:
            helper = await session.get(RunRow, spawned["id"])
            assert helper is not None
            thread = await session.get(ThreadRow, helper.thread_id)
            assert thread is not None and thread.purpose == "work"
            # Its cards and questions still reach the owner's conversation (11.6).
            assert await report_thread(session, helper) == conversation
            listed = await list_threads(session, fixture.owner, agent["id"])
            assert [row.id for row in listed] == [conversation]
        # A subagent of the owner's own request keeps its own chat, as before.
        asked = await fixture.run(agent, {"id": conversation})
        owner_context = await fixture.lease(asked)
        direct = await call(owner_context, "subagent_spawn", task="Check the CPI print")
        async with fixture.runtime.db.sessions() as session:
            helper = await session.get(RunRow, direct["id"])
            assert helper is not None
            thread = await session.get(ThreadRow, helper.thread_id)
            assert thread is not None and thread.purpose == "conversation"
    finally:
        await fixture.close()


def test_the_wake_sentence_does_not_say_no_one_is_waiting():
    from lonora_agent.context.routine import BACKGROUND

    # A Task the owner asked for is background work too; the owner may well wait on it.
    assert "no one is waiting" not in BACKGROUND
    assert "end with an empty reply" in BACKGROUND and "answer them" in BACKGROUND


@pytest.mark.asyncio
async def test_a_follow_up_of_work_the_owner_spoke_to_answers_the_owner():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Engaged desk")
        conversation = (await fixture.conversation(agent))["id"]
        work = await work_thread(fixture, agent)
        routine = await make_run(
            fixture, agent, work, "routine", metadata={"origin_thread_id": conversation}
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, routine.id, with_for_update=True)
            assert row is not None
            row.status, row.result = "completed", ""
            row.execution_state = {"owner_spoke": True}
        await returned_helper(fixture, agent, routine, "completed", "Silver held 31.")
        [follow_up] = await follow_ups(fixture, routine.id)
        # The owner answered this work; its continuation answers them too.
        assert "background" not in follow_up.model_metadata
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_rich_only_limit_report_is_not_taken_for_silence():
    database()
    from check_streaming import Fixture
    from lonora_adapter_kit.types import ModelReply
    from lonora_agent.executor import execute_run
    from lonora_agent.runtime_notices import limit_fallback
    from lonora_contracts.model_routing import ModelSelection
    from lonora_tools.loader import load_tools

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Charting desk")
        conversation = (await fixture.conversation(agent))["id"]
        work = await work_thread(fixture, agent)
        run = await make_run(
            fixture, agent, work, "routine", metadata={"origin_thread_id": conversation}
        )

        async def turn(*_: Any, **__: Any) -> Any:
            chart = {"version": 1, "parts": [{"type": "image", "url": "chart.png"}]}
            return ModelReply(text="", rich_content=chart), ModelSelection(
                provider="openai", model="background-silence-fixture"
            )

        context = await fixture.lease(
            {"id": run.id, "agent_id": run.agent_id, "thread_id": run.thread_id}
        )
        with patch("lonora_agent.tool_loop.model_turn", turn):
            await execute_run(context, load_tools(), 120, 1)
        row = await reload(fixture, run.id)
        # The model answered with something; only an empty answer is its silence.
        assert row.result == limit_fallback(False), row.result
    finally:
        await fixture.close()


async def failed_wake(fixture: Any, run: Any) -> Any:
    """The run.failed event of ``run``, as fail_run emits it."""
    from lonora_db.events import emit
    from lonora_db.schema import EventRow, RunRow
    from sqlalchemy import select

    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(RunRow, run.id, with_for_update=True)
        assert row is not None
        row.status = "failed"
        emit(
            session,
            fixture.owner,
            "run.failed",
            thread_id=row.thread_id,
            agent_id=row.agent_id,
            run_id=row.id,
            payload={"code": "runtime_error"},
        )
    async with fixture.runtime.db.sessions() as session:
        event = await session.scalar(
            select(EventRow).where(EventRow.kind == "run.failed", EventRow.run_id == run.id)
        )
        assert event is not None
        return event


@pytest.mark.asyncio
async def test_a_failed_wake_returns_exactly_the_sources_it_stood_for():
    database()
    from check_streaming import Fixture
    from lonora_db.events import emit
    from lonora_gateway.attention import projected

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Watching desk")
        conversation = (await fixture.conversation(agent))["id"]
        first = await make_run(fixture, agent, conversation, "watch", metadata={"watch_id": "w1"})
        second = await make_run(fixture, agent, conversation, "watch", metadata={"watch_id": "w1"})
        async with fixture.runtime.db.sessions() as session, session.begin():
            for run, transition in ((first, "t1"), (second, "t2")):
                emit(
                    session,
                    fixture.owner,
                    "watch.confirmed",
                    agent_id=agent["id"],
                    thread_id=conversation,
                    payload={
                        "watch_id": "w1",
                        "state": "confirmed",
                        "transition_id": transition,
                        "wakes_agent": True,
                        "woken_run_id": run.id,
                    },
                )
        # The first wake fails after the second confirmation: its own confirmation returns.
        source = await projected(fixture.runtime.db, await failed_wake(fixture, first))
        assert source.kind == "watch.confirmed" and source.payload["transition_id"] == "t1"
        assert source.payload["wakes_agent"] is False
        # A broker wake that stood for changes on two symbols returns one account item.
        work = await work_thread(fixture, agent)
        changes = [str(uuid4()), str(uuid4())]
        broker = await make_run(
            fixture,
            agent,
            work,
            "broker_event",
            metadata={"broker_event_ids": changes, "account_id": "acc"},
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            for change, symbol in zip(changes, ("XAUUSD", "EURUSD"), strict=True):
                emit(
                    session,
                    fixture.owner,
                    "broker.external_activity",
                    agent_id=agent["id"],
                    thread_id=conversation,
                    payload={
                        "id": change,
                        "account_id": "acc",
                        "symbol": symbol,
                        "wakes_agent": True,
                    },
                )
        source = await projected(fixture.runtime.db, await failed_wake(fixture, broker))
        assert source.kind == "broker.external_activity"
        assert source.payload["account_id"] == "acc" and source.payload["symbol"] is None
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_failed_helper_of_work_the_owner_spoke_to_is_still_reported():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import RunRow

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Answered desk")
        conversation = (await fixture.conversation(agent))["id"]
        watch = await make_run(fixture, agent, conversation, "watch")
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, watch.id, with_for_update=True)
            assert row is not None
            row.status, row.result = "completed", "Kept the position."
            row.execution_state = {"owner_spoke": True}
        failed = await returned_helper(fixture, agent, watch, "failed", None)
        # The owner is waiting on this work: its helper's failure reaches them.
        assert any(failed.id in text for text in await contents(fixture, conversation))
        [follow_up] = await follow_ups(fixture, watch.id)
        assert "background" not in follow_up.model_metadata
        assert follow_up.prompt == "Use the returned peer outcome to complete the owner's request."
    finally:
        await fixture.close()


def test_a_task_owned_confirmation_is_a_wake_only_for_a_task_waiting_on_it():
    from lonora_db.schema import RunRow
    from lonora_market.watchers import resumes_task

    def task_run(status: str, wait: dict[str, Any] | None) -> RunRow:
        return RunRow(status=status, execution_state={"environment": {"wait": wait}})

    waiting = {"kind": "watch", "source_id": "w2"}
    assert resumes_task(task_run("waiting_takeover", waiting), "w2")
    # Waiting on another watch, on a timer, or not waiting at all: nothing resumes, so the
    # confirmation stays the owner's item.
    assert not resumes_task(
        task_run("waiting_takeover", {"kind": "watch", "source_id": "w1"}), "w2"
    )
    assert not resumes_task(task_run("waiting_takeover", {"kind": "timer", "due_at": "x"}), "w2")
    assert not resumes_task(task_run("running", waiting), "w2")
    assert not resumes_task(task_run("waiting_input", None), "w2")


@pytest.mark.asyncio
async def test_background_work_in_a_chat_reads_its_helper_out_of_sight():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import AgentRow
    from lonora_db.workspace_wakes import wake_by_handle

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Script desk")
        conversation = (await fixture.conversation(agent))["id"]
        async with fixture.runtime.db.sessions() as session, session.begin():
            caller = await session.get(AgentRow, agent["id"])
            assert caller is not None
            wake = await wake_by_handle(session, caller, "@" + caller.name, "check the calendar")
        assert wake.thread_id == conversation
        # Its helper returns while the wake is still running.
        await fixture.lease({"id": wake.id, "agent_id": wake.agent_id, "thread_id": wake.thread_id})
        await returned_helper(fixture, agent, wake, "completed", "No events today.")
        assert await contents(fixture, conversation) == []
        # The wake reads the helper's result, finds nothing new and ends silent.
        complete, requests = router("")
        await execute(fixture, wake, complete)
        assert said(requests, "No events today.")
        row = await reload(fixture, wake.id)
        assert row.status == "completed" and row.result == ""
        assert await contents(fixture, conversation) == []
    finally:
        await fixture.close()
