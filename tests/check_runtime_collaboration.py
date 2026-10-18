"""Actual concurrent child runtimes return to one running host without a second synthesis."""

import asyncio
import json
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.collaboration.outcome_return import return_outcome
from lonora_agent.executor import execute_run
from lonora_contracts.domain import MessageCreate
from lonora_contracts.model_routing import ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.collaboration import current_session
from lonora_db.messages import send_message
from lonora_db.schema import CollaborationSessionRow, EventRow, RunRow, TradingJournalRow
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


if __name__ == "__main__":
    asyncio.run(main())
