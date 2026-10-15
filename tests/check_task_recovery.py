"""Actual Agent tool loop resumes its saved checkpoint after a provider outage."""

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.runs import Lease
from lonora_core.user_error import LonoraError
from lonora_db.runs import claim_next
from lonora_db.schema import MessageRow, RunRow
from lonora_db.task_recovery import retry_due_tasks
from lonora_db.tasks import get_task, save_task, task_state
from lonora_tools.loader import load_tools
from sqlalchemy import select


async def main():
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Recovery fixture")
        thread = await fixture.conversation(agent)
        task = await fixture.request(
            "POST",
            f"/tasks?agent_id={agent['id']}&thread_id={thread['id']}",
            {
                "title": "Read actual status then verify after recovery",
                "steps": [
                    {"id": "read", "title": "Read", "side_effect": "read_only"},
                    {"id": "verify", "title": "Verify", "side_effect": "read_only"},
                ],
                "retry_policy": {
                    "mode": "automatic",
                    "maximum_attempts": 3,
                    "initial_delay_seconds": 5,
                },
            },
        )
        registry = load_tools()
        phase = 0
        observed_calls: list[str] = []

        async def complete(
            capability: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any
        ):
            nonlocal phase
            phase += 1
            completed = [message.tool_call_id for message in messages if message.role == "tool"]
            if phase == 2:
                assert completed.count("first-status") == 1 and "first-step" in completed
                raise LonoraError("model_provider_unavailable", 502)
            if phase in {1, 3}:
                identifier = "first" if phase == 1 else "recovered"
                if phase == 3:
                    assert completed.count("first-status") == 1 and "first-step" in completed
                observed_calls.append(identifier)
                reply = ModelReply(
                    tool_calls=[
                        ToolCall(id=identifier + "-status", name="runtime_status", arguments={}),
                        ToolCall(
                            id=identifier + "-step",
                            name="task_step_update",
                            arguments={
                                "step_id": "read" if phase == 1 else "verify",
                                "plan_revision": 1,
                                "state": "completed",
                                "evidence_call_ids": [identifier + "-status"],
                            },
                        ),
                    ]
                )
            else:
                assert (
                    phase == 4
                    and completed.count("first-status") == 1
                    and completed.count("recovered-status") == 1
                )
                reply = ModelReply(text="Verified actual runtime state after recovery.")
            return reply, ModelSelection(provider="openai", model="scripted-recovery-fixture")

        async def claimed_context():
            async with fixture.runtime.db.sessions() as session, session.begin():
                run = await claim_next(session, "recovery-fixture", 120, "work")
                assert run and run.thread_id == task["work_thread_id"]
                lease = Lease(run_id=run.id, owner="recovery-fixture", fence=run.lease_fence)
                return fixture.runtime.services(fixture.owner).tool_context(
                    agent["id"], run.thread_id, lease, fixture.settings.artifact_root
                )

        first = await claimed_context()
        with patch.object(first.router, "complete", complete):
            await execute_run(first, registry, 120, 8)
            waiting = await fixture.request("GET", "/tasks/" + task["id"])
            assert waiting["status"] == "waiting" and waiting["phase"] == "retry_wait"
            assert (
                waiting["steps"][0]["state"] == "completed"
                and waiting["failure"]["recovery"] == "automatic"
            )
            live = await fixture.request("GET", f"/agents/{agent['id']}/state")
            assert live["state"] == "waiting" and live["reason_code"] == "retry_backoff"
            assert live["tasks"][0]["retry_at"] == waiting["failure"]["next_retry_at"]
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await get_task(session, fixture.owner, task["id"], lock=True)
                state = task_state(row)
                assert state.failure
                state.failure.next_retry_at = (utcnow() - timedelta(seconds=1)).isoformat()
                save_task(session, row, state)
            # Two gateway maintenance attempts cannot create parallel recovery Runs.
            assert (
                sum(
                    await asyncio.gather(
                        retry_due_tasks(fixture.runtime.db), retry_due_tasks(fixture.runtime.db)
                    )
                )
                == 1
            )
            second = await claimed_context()
            assert (
                second.lease.run_id == first.lease.run_id and second.lease.fence > first.lease.fence
            )
            await execute_run(second, registry, 120, 8)
        actual = await fixture.request("GET", "/tasks/" + task["id"])
        assert actual["status"] == "completed" and actual["attempt"] == 2
        assert all(step["state"] == "completed" for step in actual["steps"])
        assert observed_calls == ["first", "recovered"]
        async with fixture.runtime.db.sessions() as session:
            runs = list(
                await session.scalars(
                    select(RunRow).where(RunRow.thread_id == task["work_thread_id"])
                )
            )
            assert len(runs) == 1 and runs[0].status == "completed"
            messages = list(
                await session.scalars(
                    select(MessageRow).where(
                        MessageRow.thread_id == thread["id"],
                        MessageRow.content == "Verified actual runtime state after recovery.",
                    )
                )
            )
            assert len(messages) == 1
        print(
            "PASS actual AgentRuntime/tool loop/provider failure → durable backoff → two gateway recovery callers → same fenced Run/checkpoint → fresh verification → one canonical result; completed work not repeated"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
