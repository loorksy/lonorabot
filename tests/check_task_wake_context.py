"""A waking Task reads the current context head, not the one of the release it began in.

A continuous Task resumes from its checkpoint. Its constitution, the owner's
instructions and the labelled context data were written when it started; a wake
after a release or an edit must see the current text and keep its own transcript.
"""

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_agent.skills.loader import resources_root
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.tasks import TaskCreate
from lonora_db.runs import claim_next
from lonora_db.schema import AgentRow, RunRow
from lonora_db.task_wait import resume_ready_waits
from lonora_db.tasks import OWNER_ATTENTION, create_task, release_attention
from lonora_tools.loader import load_tools

OBSOLETE = "Obsolete trading policy of an earlier release."
BRIEF = "Owner brief written after the Task started: manage the euro book."


async def wake(f: Fixture, mode: str) -> None:
    agent = await f.agent("Waking Task context " + mode)
    origin = await f.conversation(agent)
    async with f.runtime.db.sessions() as session, session.begin():
        task = await create_task(
            session, f.owner, agent["id"], origin["id"], TaskCreate(title="Manage the book")
        )
        run = await session.get(RunRow, task.payload["run_id"])
        assert run
        data = {"id": run.id, "agent_id": run.agent_id, "thread_id": run.thread_id}
    policy = (resources_root() / "constitution" / "trading-policy.md").read_text()
    seen: list[list[ModelMessage]] = []

    async def complete(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
        seen.append(list(messages))
        if len(seen) == 1:
            return ModelReply(
                tool_calls=[
                    ToolCall(
                        id="durable-wait",
                        name="task_wait",
                        arguments={"kind": "timer", "seconds": 60},
                    )
                ]
            ), ModelSelection(provider="openai", model="scripted-wake")
        return ModelReply(text="Reviewed the book after the wake."), ModelSelection(
            provider="openai", model="scripted-wake"
        )

    ctx = await f.lease(data)
    with patch.object(ctx.router, "complete", complete):
        await execute_run(ctx, load_tools(), 120, 8)
        assert policy in seen[0][0].content
        async with f.runtime.db.sessions() as session, session.begin():
            current = await session.get(RunRow, ctx.lease.run_id, with_for_update=True)
            assert current and current.status == "waiting_takeover", current
            state = dict(current.execution_state)
            stored = [dict(message) for message in state["messages"]]
            # The Task began under an earlier release's constitution.
            assert policy in stored[0]["content"]
            stored[0]["content"] = stored[0]["content"].replace(policy, OBSOLETE)
            env = dict(state["environment"])
            if mode == "external_wake":
                env["wait"] = {
                    **env["wait"],
                    "due_at": (utcnow() - timedelta(seconds=1)).isoformat(),
                }
                current.execution_state = {**state, "messages": stored, "environment": env}
            else:
                # The Task was held for the owner's attention instead of waiting.
                env.pop("wait")
                current.execution_state = {
                    **state,
                    "messages": stored,
                    "environment": env,
                    "pending_input_request": {"kind": OWNER_ATTENTION, "id": "attention"},
                }
                current.status = "waiting_input"
            # The owner rewrote the agent's brief while the Task slept.
            row = await session.get(AgentRow, agent["id"], with_for_update=True)
            assert row
            row.instructions = BRIEF
        if mode == "external_wake":
            assert await resume_ready_waits(f.runtime.db) == 1
        else:
            async with f.runtime.db.sessions() as session, session.begin():
                current = await session.get(RunRow, ctx.lease.run_id, with_for_update=True)
                assert current and release_attention(current, "resume")
        async with f.runtime.db.sessions() as session, session.begin():
            claimed = await claim_next(session, "wake-worker", 120, "work")
            assert claimed and claimed.id == ctx.lease.run_id
        await execute_run(await f.lease(data), load_tools(), 120, 8)
    assert len(seen) == 2, len(seen)
    woken = seen[-1]
    system = "\n".join(message.content for message in woken if message.role == "system")
    assert OBSOLETE not in system, "the wake read the frozen constitution"
    assert policy in system and BRIEF in system, "the wake missed the current head"
    assert sum(message.content.count("<lonora_context_data>") for message in woken) <= 1
    # The Run's own transcript survives: its wait call and its result.
    assert any(call.id == "durable-wait" for message in woken for call in message.tool_calls), (
        "the transcript was lost"
    )
    assert any(message.tool_call_id == "durable-wait" for message in woken)
    if mode == "external_wake":
        assert any("<runtime_wake>" in message.content for message in woken)
    async with f.runtime.db.sessions() as session:
        current = await session.get(RunRow, ctx.lease.run_id)
        assert current and current.status == "completed", current and current.status
        persisted = current.execution_state["messages"]
        assert OBSOLETE not in persisted[0]["content"] and BRIEF in persisted[0]["content"]
    print("PASS", mode, "reads the current constitution and instructions")
    print("PASS", mode, "keeps the Task's own transcript and one context data block")


async def main() -> None:
    f = await Fixture().open()
    try:
        for mode in ("external_wake", "owner_resume"):
            await wake(f, mode)
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
