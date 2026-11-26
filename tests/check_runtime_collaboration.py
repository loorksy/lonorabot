"""Actual concurrent child runtimes return to one running host without a second synthesis;
peer outcomes returning to a finished requester share one follow-up (P1-09)."""

import asyncio
import json
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.collaboration.outcome_return import return_outcome
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
    CollaborationSessionRow,
    EventRow,
    MessageRow,
    RunRow,
    SteeringRow,
    TradingJournalRow,
)
from lonora_tools.loader import load_tools
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


async def fan_in() -> None:
    f = await Fixture().open()
    try:
        host = await f.agent("Fan-in host")
        first, second, third = (
            await f.agent("Fan-in A"),
            await f.agent("Fan-in B"),
            await f.agent("Fan-in C"),
        )
        thread = await f.conversation(host)
        parent = await f.run(host, thread)
        context = await f.lease(parent)
        a = await delegate_peer(context.for_call("fan-a"), first["id"], "Read source A")
        b = await delegate_peer(context.for_call("fan-b"), second["id"], "Read source B")
        c = await delegate_peer(context.for_call("fan-c"), third["id"], "Read source C")
        # The requester ends its turn before any helper answers.
        async with f.runtime.db.sessions() as session, session.begin():
            assert await complete_run(session, context.lease, "Asked A, B and C.", {})
        # Two children returning to the finished requester produce one follow-up, and that
        # follow-up reads both outcomes.
        await finish(f, a, "FANIN-ALPHA gold held 2400")
        await finish(f, b, "FANIN-BETA silver held 30")
        [follow_up] = await follow_ups(f, parent["id"])
        assert follow_up.status == "queued"
        follow_context = await f.lease(
            {"id": follow_up.id, "agent_id": host["id"], "thread_id": thread["id"]}
        )
        seen = "\n".join(m.content for m in await build_context(follow_context))
        assert "FANIN-ALPHA" in seen and "FANIN-BETA" in seen
        # A child returning while that follow-up runs steers it; it starts nothing new.
        await finish(f, c, "FANIN-GAMMA copper held 4")
        [same] = await follow_ups(f, parent["id"])
        assert same.id == follow_up.id
        async with f.runtime.db.sessions() as session:
            steered = list(
                await session.scalars(
                    select(MessageRow.content)
                    .join(SteeringRow, SteeringRow.message_id == MessageRow.id)
                    .where(SteeringRow.run_id == follow_up.id)
                )
            )
        assert len(steered) == 1 and "FANIN-GAMMA" in steered[0]
        # A cancelled child of a finished requester starts nothing.
        other = await f.run(host, thread)
        other_context = await f.lease(other)
        d = await delegate_peer(other_context.for_call("fan-d"), first["id"], "Read source D")
        async with f.runtime.db.sessions() as session, session.begin():
            assert await complete_run(session, other_context.lease, "Asked A.", {})
        await f.request("POST", "/runs/" + d["id"] + "/cancel", {})
        assert await follow_ups(f, other["id"]) == []
        print(
            "PASS peer outcomes returning to a finished requester share one follow-up that "
            "reads them all, a later one steers it, and a cancelled one starts nothing"
        )
    finally:
        await f.close()


async def checks() -> None:
    await main()
    await fan_in()


if __name__ == "__main__":
    asyncio.run(checks())
