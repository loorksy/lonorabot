"""Actual concurrent child runtimes return to one running host without a second synthesis;
peer outcomes returning to a finished requester share one follow-up, started once none of its
helpers is still at work (P1-09), and a repeated request that has not ended is the first one
(P3-06)."""

import asyncio
import json
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.collaboration.outcome_return import return_outcome, return_pending_outcomes
from lonora_agent.collaboration.peer_messages import delegate_peer
from lonora_agent.context.builder import build_context
from lonora_agent.executor import execute_run
from lonora_contracts.domain import MessageCreate
from lonora_contracts.model_routing import ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.collaboration import current_session
from lonora_db.messages import send_message
from lonora_db.runs import complete_run
from lonora_db.schema import (
    AgentRow,
    CollaborationSessionRow,
    EventRow,
    MessageRow,
    RunRow,
    SteeringRow,
    TradingJournalRow,
)
from lonora_tools.loader import load_tools
from lonora_tools.message import send as peer_send
from sqlalchemy import func, select


async def main() -> None:
    f = await Fixture().open()
    host_job: asyncio.Task[None] | None = None
    ready, children_done = asyncio.Event(), asyncio.Event()
    try:
        host, first, second = (
            await f.agent("Host"),
            await f.agent("Research"),
            await f.agent("Unavailable source"),
        )
        thread = await f.conversation(host)
        async with f.runtime.db.sessions() as session, session.begin():
            sent = await send_message(
                session,
                f.owner,
                thread["id"],
                MessageCreate(
                    content="Compare actual evidence", mention_agent_ids=[first["id"], second["id"]]
                ),
            )
            collaboration = await current_session(session, f.owner, thread["id"])
            assert collaboration
            session_id = collaboration.id
            child_ids = [p["run_ids"][0] for p in collaboration.state["participants"]]
            children = [await session.get(RunRow, identifier) for identifier in child_ids]
            child_data = [
                {"id": child.id, "agent_id": child.agent_id, "thread_id": child.thread_id}
                for child in children
                if child
            ]
        context = await f.lease(
            {"id": sent["run_ids"][0], "agent_id": host["id"], "thread_id": thread["id"]}
        )
        child_contexts = [await f.lease(data) for data in child_data]
        phase = 0
        selection = ModelSelection(provider="openai", model="scripted-collaboration")

        async def complete(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
            nonlocal phase
            identity = next(
                m.content for m in messages if m.content.startswith("[Lonora live routing metadata")
            )
            actor = json.loads(identity.split("Your current identity: ", 1)[1].split("\n", 1)[0])[
                "id"
            ]
            if actor == first["id"]:
                return ModelReply(
                    text="Observed bounded source A; no financial authority requested."
                ), selection
            if actor == second["id"]:
                raise LonoraError("source_unavailable", 503)
            phase += 1
            if phase == 1:
                ready.set()
                await children_done.wait()
                return ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="inspect-round",
                            name="collaboration_inspect",
                            arguments={"session_id": session_id},
                        )
                    ]
                ), selection
            if phase == 2:
                result = next(
                    json.loads(m.content) for m in messages if m.tool_call_id == "inspect-round"
                )
                assert sorted(r["status"] for r in result["round_outcomes"]) == [
                    "completed",
                    "failed",
                ]
                assert any("Observed bounded source A" in m.content for m in messages)
                return ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="finish-round",
                            name="collaboration_finish",
                            arguments={
                                "session_id": session_id,
                                "final_result": "Source A observed; source B unavailable, no invented consensus.",
                            },
                        )
                    ]
                ), selection
            assert phase == 3
            return ModelReply(
                text="Source A is available; B failed. Analysis remains bounded by that evidence."
            ), selection

        with patch.object(context.router, "complete", complete):
            host_job = asyncio.create_task(execute_run(context, load_tools(), 120, 8))
            await asyncio.wait_for(ready.wait(), 10)
            await asyncio.gather(
                *(execute_run(child, load_tools(), 120, 4) for child in child_contexts)
            )
            await asyncio.gather(
                *(return_outcome(f.runtime.db, identifier) for identifier in child_ids)
            )
            children_done.set()
            await asyncio.wait_for(host_job, 20)
        async with f.runtime.db.sessions() as session:
            row = await session.get(CollaborationSessionRow, session_id)
            run = await session.get(RunRow, context.lease.run_id)
            assert row and row.state["status"] == "completed"
            assert row.state["rounds"][0]["synthesis_run_id"] == context.lease.run_id
            assert run and run.status == "completed" and phase == 3
            assert (
                await session.scalar(
                    select(func.count()).select_from(RunRow).where(RunRow.thread_id == thread["id"])
                )
                == 1
            )
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(EventRow)
                    .where(EventRow.kind == "collaboration.completed")
                )
                == 1
            )
            assert await session.scalar(select(func.count()).select_from(TradingJournalRow)) == 0
        print(
            "PASS two actual peer runtimes (success/failure), duplicate outcome delivery, active-host continuation and exactly one synthesis without authority transfer"
        )
    finally:
        children_done.set()
        if host_job and not host_job.done():
            host_job.cancel()
            await asyncio.gather(host_job, return_exceptions=True)
        await f.close()


async def follow_ups(f: Fixture, parent_id: str) -> list[RunRow]:
    async with f.runtime.db.sessions() as session:
        return list(
            await session.scalars(
                select(RunRow).where(
                    RunRow.parent_run_id == parent_id, RunRow.trigger == "follow_up"
                )
            )
        )


async def finish(f: Fixture, run: dict[str, Any], answer: str) -> None:
    """``run`` ends with ``answer`` and its outcome returns, as the worker does."""
    context = await f.lease(run)
    async with f.runtime.db.sessions() as session, session.begin():
        assert await complete_run(session, context.lease, answer, {})
    await return_outcome(f.runtime.db, run["id"])


async def rest(f: Fixture, run: dict[str, Any]) -> None:
    """``run`` stops short of an outcome: it waits for the owner's answer."""
    async with f.runtime.db.sessions() as session, session.begin():
        row = await session.get(RunRow, run["id"], with_for_update=True)
        assert row is not None
        row.status = "waiting_input"


async def steered(f: Fixture, run_id: str) -> list[str]:
    async with f.runtime.db.sessions() as session:
        return list(
            await session.scalars(
                select(MessageRow.content)
                .join(SteeringRow, SteeringRow.message_id == MessageRow.id)
                .where(SteeringRow.run_id == run_id)
            )
        )


async def fan_in() -> None:
    f = await Fixture().open()
    try:
        host = await f.agent("Fan-in host")
        first, second, third, fourth = (
            await f.agent("Fan-in A"),
            await f.agent("Fan-in B"),
            await f.agent("Fan-in C"),
            await f.agent("Fan-in D"),
        )
        thread = await f.conversation(host)
        parent = await f.run(host, thread)
        context = await f.lease(parent)
        a = await delegate_peer(context.for_call("fan-a"), first["id"], "Read source A")
        b = await delegate_peer(context.for_call("fan-b"), second["id"], "Read source B")
        # Through the tool: its result tells the requester the outcome comes back on its own.
        c = await peer_send(
            context.for_call("fan-c"), {"agent_id": third["id"], "task": "Read source C"}
        )
        assert c["next"].startswith("The outcome returns here on its own")
        d = await delegate_peer(context.for_call("fan-d"), fourth["id"], "Read source D")
        # Another task to the same agent is another request.
        e = await delegate_peer(context.for_call("fan-e"), first["id"], "Read source E")
        # The same request to the same agent, while the first is not done, is the first (P3-06).
        again = await delegate_peer(context.for_call("fan-a-again"), first["id"], "Read source A")
        assert again["id"] == a["id"] and again["duplicate"] is True and "duplicate" not in a
        async with f.runtime.db.sessions() as session:
            asked = await session.scalar(
                select(func.count())
                .select_from(RunRow)
                .where(RunRow.parent_run_id == parent["id"], RunRow.trigger == "peer")
            )
            written = await session.scalar(
                select(func.count())
                .select_from(MessageRow)
                .where(MessageRow.thread_id == thread["id"], MessageRow.content == "Read source A")
            )
        assert asked == 5 and written == 1
        # The requester ends its turn before any helper answers.
        async with f.runtime.db.sessions() as session, session.begin():
            assert await complete_run(session, context.lease, "Asked A to E.", {})
        # D and E wait for the owner: a helper that waits holds back no answer.
        await rest(f, d)
        await rest(f, e)
        # An outcome that returns while another helper is still at work starts nothing,
        # however long that helper takes; the last one back starts the one follow-up.
        await finish(f, a, "FANIN-ALPHA gold held 2400")
        assert await follow_ups(f, parent["id"]) == []
        await finish(f, b, "FANIN-BETA silver held 30")
        assert await follow_ups(f, parent["id"]) == []
        await finish(f, c, "FANIN-GAMMA copper held 4")
        [follow_up] = await follow_ups(f, parent["id"])
        assert follow_up.status == "queued"
        assert follow_up.prompt == "Use the returned peer outcomes to complete the owner's request."
        # A helper cancelled while that follow-up has not started joins it and starts nothing.
        await f.request("POST", "/runs/" + e["id"] + "/cancel", {})
        [same] = await follow_ups(f, parent["id"])
        assert same.id == follow_up.id and same.status == "queued"
        follow_context = await f.lease(
            {"id": follow_up.id, "agent_id": host["id"], "thread_id": thread["id"]}
        )
        seen = "\n".join(m.content for m in await build_context(follow_context))
        assert all(f"FANIN-{word}" in seen for word in ("ALPHA", "BETA", "GAMMA")), seen
        assert f"run_id='{e['id']}' status='cancelled'" in seen
        # A helper returning while that follow-up runs steers it; it starts nothing new.
        await finish(f, d, "FANIN-DELTA platinum held 9")
        [same] = await follow_ups(f, parent["id"])
        assert same.id == follow_up.id
        [card] = await steered(f, follow_up.id)
        assert "FANIN-DELTA" in card
        # A cancelled child of a finished requester starts nothing.
        other = await f.run(host, thread)
        other_context = await f.lease(other)
        gone = await delegate_peer(other_context.for_call("fan-f"), first["id"], "Read source F")
        async with f.runtime.db.sessions() as session, session.begin():
            assert await complete_run(session, other_context.lease, "Asked A.", {})
        await f.request("POST", "/runs/" + gone["id"] + "/cancel", {})
        assert await follow_ups(f, other["id"]) == []
        # Ended work is sent again by a new request.
        later = await f.run(host, thread)
        later_context = await f.lease(later)
        ended = await delegate_peer(later_context.for_call("fan-g"), first["id"], "Read source G")
        await f.request("POST", "/runs/" + ended["id"] + "/cancel", {})
        resent = await delegate_peer(
            later_context.for_call("fan-g-again"), first["id"], "Read source G"
        )
        assert resent["id"] != ended["id"] and "duplicate" not in resent
        print(
            "PASS peer outcomes returning to a finished requester wait for its helpers still "
            "at work and share one follow-up that reads them all; a cancelled one joins it, a "
            "later one steers it, and a cancelled one alone starts nothing; a repeated "
            "unfinished request is the first, an ended one is sent again"
        )
    finally:
        await f.close()


async def paused(f: Fixture, agent: dict[str, Any], value: bool) -> None:
    async with f.runtime.db.sessions() as session, session.begin():
        row = await session.get(AgentRow, agent["id"], with_for_update=True)
        assert row is not None
        row.paused = value


async def held_fan_in() -> None:
    f = await Fixture().open()
    try:
        host, gold, silver = (
            await f.agent("Held host"),
            await f.agent("Held gold"),
            await f.agent("Held silver"),
        )
        thread = await f.conversation(host)
        parent = await f.run(host, thread)
        context = await f.lease(parent)
        asked = await delegate_peer(context.for_call("held-gold"), gold["id"], "Read gold")
        await delegate_peer(context.for_call("held-silver"), silver["id"], "Read silver")
        async with f.runtime.db.sessions() as session, session.begin():
            assert await complete_run(session, context.lease, "Asked gold and silver.", {})
        await finish(f, asked, "HELD-GOLD 2400")
        # The maintenance pass leaves a fan-in alone while a helper is still at work.
        await return_pending_outcomes(f.runtime.db)
        assert await follow_ups(f, parent["id"]) == []
        # The silver agent is paused: its request waits for the resume and holds back no
        # answer. The paused host's own follow-up waits for its resume (4.7.1); then the
        # next pass starts the one follow-up.
        await paused(f, silver, True)
        await paused(f, host, True)
        await return_pending_outcomes(f.runtime.db)
        assert await follow_ups(f, parent["id"]) == []
        await paused(f, host, False)
        await return_pending_outcomes(f.runtime.db)
        [follow_up] = await follow_ups(f, parent["id"])
        follow_context = await f.lease(
            {"id": follow_up.id, "agent_id": host["id"], "thread_id": thread["id"]}
        )
        seen = "\n".join(m.content for m in await build_context(follow_context))
        assert "HELD-GOLD" in seen
        await paused(f, silver, False)
        print(
            "PASS a held fan-in whose last helper is paused starts its one follow-up on the "
            "next maintenance pass, never while a helper is still at work or its requester "
            "is paused"
        )
    finally:
        await f.close()


async def beside_collaboration() -> None:
    f = await Fixture().open()
    try:
        host, first, second = (
            await f.agent("Beside host"),
            await f.agent("Beside A"),
            await f.agent("Beside B"),
        )
        thread = await f.conversation(host)
        async with f.runtime.db.sessions() as session, session.begin():
            sent = await send_message(
                session,
                f.owner,
                thread["id"],
                MessageCreate(
                    content="Compare the evidence", mention_agent_ids=[first["id"], second["id"]]
                ),
            )
            collaboration = await current_session(session, f.owner, thread["id"])
            assert collaboration
            participant = await session.get(
                RunRow, collaboration.state["participants"][0]["run_ids"][0]
            )
            assert participant is not None
            participant_id, target, subject = (
                participant.id,
                participant.agent_id,
                participant.prompt,
            )
        context = await f.lease(
            {"id": sent["run_ids"][0], "agent_id": host["id"], "thread_id": thread["id"]}
        )
        # A collaboration participant answers its round, not a plain request: the same
        # words sent with peer_send are a request of their own.
        plain = await delegate_peer(context.for_call("beside-peer"), target, subject)
        assert plain["id"] != participant_id and "duplicate" not in plain
        print("PASS a plain peer request is never a collaboration participant's duplicate")
    finally:
        await f.close()


async def checks() -> None:
    await main()
    await fan_in()
    await held_fan_in()
    await beside_collaboration()


if __name__ == "__main__":
    asyncio.run(checks())
