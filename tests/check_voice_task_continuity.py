"""Scripted voice sideband → real AgentRuntime → same durable Task across calls.

No microphone, provider or broker network is used. Native Android acceptance is
separate; these checks exercise the resident sideband, PostgreSQL admission,
global router/tool loop, truthful status, steering and outcome delivery.
"""

import asyncio
import json
import time
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.model_routing import ModelSelection
from lonora_db.schema import MessageRow, RunRow, TradingJournalRow, VoiceSessionRow
from lonora_db.tasks import get_task, snapshot
from lonora_tools.loader import load_tools
from lonora_voice.barge_in import barge_in
from lonora_voice.realtime import (
    TRANSCRIPT_HANDOFF_TIMEOUT_SECONDS,
    TRANSCRIPT_STABILITY_SECONDS,
    RealtimeVoiceSession,
)
from lonora_voice.sessions import end_voice_session
from sqlalchemy import func, select


async def main() -> None:
    fixture = await Fixture().open()
    background: asyncio.Task[None] | None = None
    continue_work = asyncio.Event()
    try:
        agent = await fixture.agent("Same voice/text agent")
        thread = await fixture.conversation(agent)
        registry = load_tools()
        services = fixture.runtime.services(fixture.owner)
        title = "Inspect durable voice-task evidence"
        description = "Read actual runtime state, then verify it after owner steering."
        initial = "Analyze the available evidence and keep working while I leave the call."
        status_request = "Where did you get to with that analysis?"
        revision_request = "Focus the remaining verification on the one-minute view."
        task_id = ""
        task_snapshot: dict[str, Any] = {}
        work_waiting = asyncio.Event()
        work_turns = 0
        actual_status: dict[str, Any] = {}

        async def resident() -> RealtimeVoiceSession:
            # The paid admission/transport contract is covered by tests/voice;
            # this is the already-attached resident Gateway sideband boundary.
            identifier = str(uuid4())
            async with fixture.runtime.db.sessions() as session, session.begin():
                session.add(
                    VoiceSessionRow(
                        id=identifier,
                        owner_id=fixture.owner,
                        agent_id=agent["id"],
                        thread_id=thread["id"],
                        payload={"mode": "gpt_live", "status": "connected"},
                        state={
                            "gateway": "continuity-fixture",
                            "input": [],
                            "output": [],
                            "delegations": {},
                            "input_offset": -1,
                            "last_activity": time.time(),
                        },
                    )
                )
            return RealtimeVoiceSession(
                fixture.runtime.db,
                services.router.credentials,
                identifier,
                "continuity-fixture",
            )

        async def utterance(
            voice: RealtimeVoiceSession,
            identifier: str,
            text: str,
            start: int,
            end: int,
        ) -> list[str]:
            await voice.update(
                {
                    "type": "session.input_transcript.delta",
                    "event_id": identifier + "-speech",
                    "start_ms": start,
                    "end_ms": end,
                    "delta": text,
                }
            )
            await voice.update(
                {
                    "type": "session.delegation.created",
                    "offset_ms": end,
                    "delegation": {"id": identifier, "target": "client"},
                }
            )
            # Exercise the real scheduling grace; it is not semantic finality.
            await asyncio.sleep(TRANSCRIPT_STABILITY_SECONDS + 0.05)
            await asyncio.gather(voice.delegate(), voice.delegate())
            async with fixture.runtime.db.sessions() as session:
                row = await session.get(VoiceSessionRow, voice.session_id)
                assert row and row.thread_id == thread["id"] and row.agent_id == agent["id"]
                return list(row.state["delegations"][identifier].get("run_ids", []))

        def results(messages: list[ModelMessage]) -> dict[str, dict[str, Any]]:
            return {
                message.tool_call_id: json.loads(message.content)
                for message in messages
                if message.role == "tool" and message.tool_call_id
            }

        async def complete(
            _capability: Any, messages: list[ModelMessage], _tools: Any, **_kwargs: Any
        ):
            nonlocal task_id, task_snapshot, work_turns, actual_status
            completed = results(messages)
            is_work = any(
                message.role == "user" and message.content == title + "\n" + description
                for message in messages
            )
            if is_work:
                work_turns += 1
                if work_turns == 1:
                    reply = ModelReply(
                        tool_calls=[
                            ToolCall(id="first-evidence", name="runtime_status", arguments={}),
                            ToolCall(
                                id="first-step",
                                name="task_step_update",
                                arguments={
                                    "step_id": "read",
                                    "plan_revision": 1,
                                    "state": "completed",
                                    "evidence_call_ids": ["first-evidence"],
                                },
                            ),
                        ]
                    )
                elif work_turns == 2:
                    assert completed["first-step"]["steps"][0]["state"] == "completed"
                    work_waiting.set()
                    await asyncio.wait_for(continue_work.wait(), 30)
                    reply = ModelReply(
                        tool_calls=[
                            ToolCall(id="fresh-evidence", name="runtime_status", arguments={})
                        ]
                    )
                elif work_turns == 3:
                    revision = next(
                        message.content
                        for message in reversed(messages)
                        if "<task_plan_revision>" in message.content
                    )
                    assert '"plan_revision":2' in revision and revision_request in revision
                    reply = ModelReply(
                        tool_calls=[
                            ToolCall(
                                id="verify-step",
                                name="task_step_update",
                                arguments={
                                    "step_id": "verify",
                                    "plan_revision": 2,
                                    "state": "completed",
                                    "evidence_call_ids": ["fresh-evidence"],
                                },
                            )
                        ]
                    )
                else:
                    assert work_turns == 4 and completed["verify-step"]["plan_revision"] == 2
                    reply = ModelReply(
                        text="Completed the same analysis after the one-minute revision."
                    )
            else:
                latest = next(
                    message.content for message in reversed(messages) if message.role == "user"
                )
                if latest == initial:
                    if "start-durable-work" not in completed:
                        reply = ModelReply(
                            tool_calls=[
                                ToolCall(
                                    id="start-durable-work",
                                    name="task_start",
                                    arguments={
                                        "title": title,
                                        "description": description,
                                        "steps": [
                                            {
                                                "id": "read",
                                                "title": "Read",
                                                "side_effect": "read_only",
                                            },
                                            {
                                                "id": "verify",
                                                "title": "Verify",
                                                "side_effect": "read_only",
                                            },
                                        ],
                                    },
                                )
                            ]
                        )
                    else:
                        task_snapshot = completed["start-durable-work"]
                        task_id = task_snapshot["id"]
                        assert task_snapshot["status"] == "queued"
                        reply = ModelReply(
                            text="I have started the analysis and will continue working."
                        )
                elif latest == status_request:
                    if "actual-task-status" not in completed:
                        reply = ModelReply(
                            tool_calls=[
                                ToolCall(
                                    id="actual-task-status",
                                    name="task_inspect",
                                    arguments={"task_id": task_id},
                                )
                            ]
                        )
                    else:
                        actual_status = completed["actual-task-status"]["tasks"][0]
                        assert actual_status["status"] == "running"
                        assert actual_status["steps"][0]["state"] == "completed"
                        assert actual_status["steps"][1]["state"] == "pending"
                        reply = ModelReply(
                            text="The evidence read is complete; verification is still pending."
                        )
                else:
                    assert latest == revision_request
                    if "inspect-before-revision" not in completed:
                        reply = ModelReply(
                            tool_calls=[
                                ToolCall(
                                    id="inspect-before-revision",
                                    name="task_inspect",
                                    arguments={"task_id": task_id},
                                )
                            ]
                        )
                    elif "revise-same-task" not in completed:
                        current = completed["inspect-before-revision"]["tasks"][0]
                        reply = ModelReply(
                            tool_calls=[
                                ToolCall(
                                    id="revise-same-task",
                                    name="task_control",
                                    arguments={
                                        "task_id": task_id,
                                        "action": "revise",
                                        "expected_version": current["version"],
                                        "instruction": revision_request,
                                    },
                                )
                            ]
                        )
                    else:
                        assert completed["revise-same-task"]["id"] == task_id
                        assert completed["revise-same-task"]["plan_revision"] == 2
                        reply = ModelReply(
                            text="The remaining verification now uses the one-minute focus."
                        )
            return reply, ModelSelection(provider="openai", model="scripted-voice-continuity")

        voice = await resident()
        async with fixture.runtime.db.sessions() as session:
            journal_before = await session.scalar(
                select(func.count()).select_from(TradingJournalRow)
            )
        await voice.update(
            {
                "type": "session.input_transcript.delta",
                "event_id": "partial-buy",
                "start_ms": 0,
                "end_ms": 100,
                "delta": "Buy ",
            }
        )
        await voice.delegate()
        async with fixture.runtime.db.sessions() as session:
            assert not await session.scalar(
                select(RunRow.id).where(RunRow.thread_id == thread["id"])
            )
            assert not await session.scalar(
                select(MessageRow.id).where(MessageRow.thread_id == thread["id"])
            )
        # A delegation boundary ahead of the available transcript also fails closed.
        await voice.update(
            {
                "type": "session.delegation.created",
                "offset_ms": 800,
                "delegation": {"id": "incomplete-buy", "target": "client"},
            }
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(VoiceSessionRow, voice.session_id, with_for_update=True)
            assert row
            state = json.loads(json.dumps(row.state))
            state["delegations"]["incomplete-buy"]["received_at"] = (
                time.time() - TRANSCRIPT_HANDOFF_TIMEOUT_SECONDS - 1
            )
            row.state = state
        await voice.delegate()
        async with fixture.runtime.db.sessions() as session:
            assert not await session.scalar(
                select(RunRow.id).where(RunRow.thread_id == thread["id"])
            )
            assert (
                await session.scalar(select(func.count()).select_from(TradingJournalRow))
                == journal_before
            )
        print(
            "PASS partial/incomplete financial speech creates no Message, Run or financial journal",
            flush=True,
        )

        with patch.object(services.router, "complete", complete):
            initial_ids = await utterance(voice, "analysis", initial, 900, 2400)
            assert len(initial_ids) == 1
            context = await fixture.lease(
                {"id": initial_ids[0], "agent_id": agent["id"], "thread_id": thread["id"]}
            )
            await execute_run(context, registry, 120, 12)
            assert task_id
            task = await fixture.request("GET", "/tasks/" + task_id)
            assert task["status"] == "queued" and task["origin_thread_id"] == thread["id"]
            work_id = task["runs"][0]["id"]
            work = await fixture.lease(
                {"id": work_id, "agent_id": agent["id"], "thread_id": task["work_thread_id"]}
            )
            background = asyncio.create_task(execute_run(work, registry, 120, 12))
            await asyncio.wait_for(work_waiting.wait(), 20)
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(VoiceSessionRow, voice.session_id, with_for_update=True)
                assert row
                row.state = {**row.state, "last_activity": time.time() - 31}
            assert await voice.tick()
            assert (
                await barge_in(
                    fixture.runtime.db, fixture.owner, thread["id"], session_id=voice.session_id
                )
                == []
            )
            await end_voice_session(fixture.runtime.db, fixture.owner, voice.session_id)
            assert not await voice.tick()
            task = await fixture.request("GET", "/tasks/" + task_id)
            assert task["status"] == "running" and task["runs"][0]["id"] == work_id
            print(
                "PASS spoken acknowledgement, silence, barge-in and call disconnect preserve active durable work",
                flush=True,
            )

            reconnected = await resident()
            status_ids = await utterance(reconnected, "status", status_request, 0, 1000)
            context = await fixture.lease(
                {"id": status_ids[0], "agent_id": agent["id"], "thread_id": thread["id"]}
            )
            await execute_run(context, registry, 120, 12)
            assert actual_status["id"] == task_id and actual_status["runs"][0]["id"] == work_id
            revised_ids = await utterance(reconnected, "revision", revision_request, 1100, 2500)
            context = await fixture.lease(
                {"id": revised_ids[0], "agent_id": agent["id"], "thread_id": thread["id"]}
            )
            await execute_run(context, registry, 120, 12)
            continue_work.set()
            await asyncio.wait_for(background, 20)
            task = await fixture.request("GET", "/tasks/" + task_id)
            assert task["status"] == "completed" and task["plan_revision"] == 2
            assert all(step["state"] == "completed" for step in task["steps"])
            assert len(task["runs"]) == 1 and task["runs"][0]["id"] == work_id
            async with fixture.runtime.db.sessions() as session:
                stored = await session.get(RunRow, work_id)
                assert stored
                completed_ids = [
                    m.get("tool_call_id")
                    for m in stored.execution_state["messages"]
                    if m.get("role") == "tool"
                ]
                assert (
                    completed_ids.count("first-evidence")
                    == completed_ids.count("fresh-evidence")
                    == 1
                )
                final_count = await session.scalar(
                    select(func.count())
                    .select_from(MessageRow)
                    .where(
                        MessageRow.thread_id == thread["id"],
                        MessageRow.content
                        == "Completed the same analysis after the one-minute revision.",
                    )
                )
                assert final_count == 1
                assert (await snapshot(session, await get_task(session, fixture.owner, task_id)))[
                    "status"
                ] == "completed"
            await end_voice_session(fixture.runtime.db, fixture.owner, reconnected.session_id)
            assert not await reconnected.tick()
        print(
            "PASS reconnected voice inspects actual Task progress, steers the same Task and returns one evidence-backed result; completed work is not replayed",
            flush=True,
        )
    finally:
        continue_work.set()
        if background and not background.done():
            background.cancel()
            await asyncio.gather(background, return_exceptions=True)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
