"""Disposable PostgreSQL regression: actual admission, tool loop and completion, scripted model."""

import asyncio
import json
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.context.group import group_context
from lonora_agent.executor import execute_run
from lonora_contracts.model_routing import ModelSelection
from lonora_db.schema import AgentRow, MessageRow, RunRow
from lonora_tools.registry import ToolRegistry
from lonora_tools.runtime_control import tools
from sqlalchemy import select


async def checks() -> None:
    fixture = await Fixture().open()
    try:
        lead = await fixture.agent("Paused lead")
        active = await fixture.agent("Available specialist")
        group = await fixture.request(
            "POST",
            "/groups/create",
            {
                "name": "Group reply regression",
                "member_ids": [lead["id"], active["id"]],
                "participation": "mentions_or_lead",
            },
        )
        fixture.groups.append(group["id"])
        fixture.group_threads.append(group["thread_id"])
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(AgentRow, lead["id"])
            assert row is not None
            row.paused = True
            rendered = await group_context(session, group["id"], active["id"])
            assert active["name"] in rendered and active["id"] in rendered

        async def execute(replies: list[ModelReply], trigger: str = "group") -> dict[str, Any]:
            admitted = await fixture.request(
                "POST",
                f"/threads/{group['thread_id']}/messages",
                {
                    "content": "Give your market analysis",
                    "client_nonce": uuid4().hex,
                },
            )
            assert len(admitted["run_ids"]) == 1
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(RunRow, admitted["run_ids"][0])
                assert row is not None and row.agent_id == active["id"]
                row.trigger = trigger
                row.execution_state = {
                    "messages": [
                        ModelMessage(
                            role="user", content="Explicit scripted fixture request"
                        ).model_dump(mode="json")
                    ]
                }
                run = {"id": row.id, "agent_id": row.agent_id, "thread_id": row.thread_id}
            context = await fixture.lease(run)
            seen: list[list[ModelMessage]] = []

            async def model(*args: Any, **kwargs: Any):
                seen.append(list(args[1]))
                assert replies, "Unexpected extra model request"
                return replies.pop(0), ModelSelection(provider="openai", model="scripted-fixture")

            with patch("lonora_agent.tool_loop.model_turn", model):
                await execute_run(context, ToolRegistry(tools()), 90, 8)
            async with fixture.runtime.db.sessions() as session:
                row = await session.get(RunRow, run["id"])
                assert row is not None and row.status == "completed", (
                    row.error_code if row else "missing"
                )
                messages = list(
                    await session.scalars(
                        select(MessageRow).where(
                            MessageRow.thread_id == run["thread_id"],
                            MessageRow.agent_id == active["id"],
                        )
                    )
                )
                return {
                    "result": row.result,
                    "metadata": row.model_metadata,
                    "seen": seen,
                    "messages": messages,
                }

        silence = ModelReply(
            tool_calls=[ToolCall(id="silence", name="group_silence", arguments={})]
        )
        result = await execute([silence, ModelReply(text="Actual selected agent response")])
        assert result["result"] == "Actual selected agent response"
        assert any(
            '"code": "reply_required"' in m.content for m in result["seen"][1] if m.role == "tool"
        )
        assert result["messages"][-1].content == result["result"]

        result = await execute(
            [ModelReply(), ModelReply(text="Actual response after empty completion")]
        )
        assert result["result"] == "Actual response after empty completion"
        assert [m.content for m in result["seen"][1] if m.role == "user"] == [
            "Explicit scripted fixture request"
        ]

        result = await execute(
            [silence, ModelReply(text="Returned teammate result relayed")], "follow_up"
        )
        assert result["result"] == "Returned teammate result relayed"

        result = await execute([silence], "watch")
        assert result["result"] == "" and result["metadata"]["reply_outcome"] == "silent"

        result = await execute(
            [ModelReply(text="Report already written", tool_calls=silence.tool_calls)], "watch"
        )
        assert result["result"] == "Report already written"
        assert result["metadata"]["reply_outcome"] == "answered"

        direct = await fixture.conversation(active)
        direct_run = await fixture.run(active, direct)
        direct_context = await fixture.lease(direct_run)
        refused = await ToolRegistry(tools()).execute(silence.tool_calls[0], direct_context)
        assert refused["code"] == "silence_requires_group"
        async with fixture.runtime.db.sessions() as session, session.begin():
            direct_row = await session.get(RunRow, direct_run["id"])
            assert direct_row is not None
            direct_row.trigger = "watch"
        no_report = await ToolRegistry(tools()).execute(silence.tool_calls[0], direct_context)
        assert no_report["_runtime_silence"]

        previous = result["messages"][-1]
        reply = await fixture.request(
            "POST",
            f"/threads/{group['thread_id']}/messages",
            {
                "content": "Explain that result",
                "reply_to": previous.id,
                "client_nonce": uuid4().hex,
            },
        )
        async with fixture.runtime.db.sessions() as session:
            routed = await session.get(RunRow, reply["run_ids"][0])
            assert routed is not None and routed.agent_id == active["id"]
        print(
            json.dumps(
                {"checks": 9, "result": "passed", "provider": "scripted; no real model calls"}
            )
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(checks())
