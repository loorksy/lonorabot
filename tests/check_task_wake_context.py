"""A waking Task reads the current context head, not the one of the release it began in.

A continuous Task resumes from its checkpoint. Its constitution, the owner's
instructions and the labelled context data were written when it started; a wake
after a release or an edit must see the current text and keep its own transcript.
"""

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_agent.skills.loader import resources_root
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.tasks import TaskCreate
from lonora_core.user_error import LonoraError
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
            # The Run viewed a skill before it slept; its procedure must stay in force.
            state["viewed_skill_ids"] = ["position-management"]
            env = dict(state["environment"])
            if mode != "owner_resume":
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
        if mode != "owner_resume":
            assert await resume_ready_waits(f.runtime.db) == 1
        else:
            async with f.runtime.db.sessions() as session, session.begin():
                current = await session.get(RunRow, ctx.lease.run_id, with_for_update=True)
                assert current and release_attention(current, "resume")
        async with f.runtime.db.sessions() as session, session.begin():
            claimed = await claim_next(session, "wake-worker", 120, "work")
            assert claimed and claimed.id == ctx.lease.run_id
        if mode == "rebuild_fails":

            async def unavailable(*_: object) -> list[ModelMessage]:
                raise LonoraError("policy_resource_missing", 500)

            with patch("lonora_agent.loop_restore.build_context", unavailable):
                await execute_run(await f.lease(data), load_tools(), 120, 8)
        else:
            await execute_run(await f.lease(data), load_tools(), 120, 8)
    assert len(seen) == 2, len(seen)
    woken = seen[-1]
    system = "\n".join(message.content for message in woken if message.role == "system")
    if mode == "rebuild_fails":
        # The wake is delivered on the frozen head rather than failing the Task.
        assert OBSOLETE in system and BRIEF not in system
    else:
        assert OBSOLETE not in system, "the wake read the frozen constitution"
        assert policy in system and BRIEF in system, "the wake missed the current head"
    assert sum(message.content.count("<lonora_context_data>") for message in woken) <= 1
    # The Run's own transcript survives: its wait call and its result.
    calls = [call.id for message in woken for call in message.tool_calls]
    assert calls.count("durable-wait") == 1, "the transcript was lost or duplicated"
    assert [message.tool_call_id for message in woken].count("durable-wait") == 1
    if mode != "owner_resume":
        assert any("<runtime_wake>" in message.content for message in woken)
    async with f.runtime.db.sessions() as session:
        current = await session.get(RunRow, ctx.lease.run_id)
        assert current and current.status == "completed", current and current.status
        persisted = current.execution_state["messages"]
        if mode == "rebuild_fails":
            print("PASS a head that cannot be rebuilt keeps the frozen one; the wake still runs")
            return
        assert OBSOLETE not in persisted[0]["content"] and BRIEF in persisted[0]["content"]
        assert "position-management" in current.execution_state["instruction_skill_ids"]
    print("PASS", mode, "reads the current constitution and instructions")
    print("PASS", mode, "keeps the Task's own transcript, its viewed skill and one context block")


async def owner_answer(f: Fixture) -> None:
    """The owner's answer to a pending question wakes the Run: it reads the head of now."""
    agent = await f.agent("Waking question")
    thread = await f.conversation(agent)
    run = await f.run(agent, thread)
    policy = (resources_root() / "constitution" / "trading-policy.md").read_text()
    choices = [{"id": "yes", "label": "Yes"}, {"id": "no", "label": "No"}]
    seen: list[list[ModelMessage]] = []

    async def complete(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
        seen.append(list(messages))
        if len(seen) == 1:
            return ModelReply(
                tool_calls=[
                    ToolCall(
                        id="question",
                        name="wait_for_input",
                        arguments={"question": "Add to the position?", "choices": choices},
                    )
                ]
            ), ModelSelection(provider="openai", model="scripted-wake")
        return ModelReply(text="Added nothing; reviewed the book."), ModelSelection(
            provider="openai", model="scripted-wake"
        )

    ctx = await f.lease(run)
    with patch.object(ctx.router, "complete", complete):
        await execute_run(ctx, load_tools(), 120, 8)
        async with f.runtime.db.sessions() as session, session.begin():
            current = await session.get(RunRow, run["id"], with_for_update=True)
            assert current and current.status == "waiting_input", current
            stored = [dict(message) for message in current.execution_state["messages"]]
            stored[0]["content"] = stored[0]["content"].replace(policy, OBSOLETE)
            current.execution_state = {**current.execution_state, "messages": stored}
            row = await session.get(AgentRow, agent["id"], with_for_update=True)
            assert row
            row.instructions = BRIEF
        question = (await f.request("GET", "/runs/" + run["id"]))["input_request"]
        await f.request(
            "POST",
            f"/threads/{thread['id']}/messages",
            {
                "content": "Yes",
                "client_nonce": uuid4().hex,
                "reply_to": question["message_id"],
                "input_answer": {
                    "run_id": run["id"],
                    "question_id": question["id"],
                    "choice_id": "yes",
                },
            },
        )
        await execute_run(await f.lease(run), load_tools(), 120, 8)
    assert len(seen) == 2, len(seen)
    system = "\n".join(message.content for message in seen[-1] if message.role == "system")
    assert OBSOLETE not in system and policy in system and BRIEF in system
    print("PASS an owner's answer to a pending question reads the current head")


async def main() -> None:
    f = await Fixture().open()
    try:
        for mode in ("external_wake", "owner_resume", "rebuild_fails"):
            await wake(f, mode)
        await owner_answer(f)
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
