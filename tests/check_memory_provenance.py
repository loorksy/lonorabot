"""Memory authorship is server-derived; legacy content is never relabeled owner fact."""

import asyncio
import json
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.model_routing import ModelSelection
from lonora_db.memory import memory_provenance
from lonora_tools.loader import load_tools


async def main() -> None:
    f = await Fixture().open()
    try:
        agent = await f.agent("Memory provenance")
        thread = await f.conversation(agent)
        async with f.runtime.db.sessions() as session:
            assert (await memory_provenance(session, agent["id"], 1))["source"] == "legacy_unknown"
        initial = await f.request("GET", f"/agents/{agent['id']}/memory")
        await f.request(
            "PUT",
            f"/agents/{agent['id']}/memory",
            {"version": initial["version"], "content": "Owner preference: concise replies"},
        )
        ctx = await f.lease(await f.run(agent, thread))
        phase = 0

        async def complete(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
            nonlocal phase
            phase += 1
            call = None
            if phase == 1:
                call = ToolCall(id="owner-read", name="memory_read", arguments={})
            elif phase == 2:
                result = json.loads(messages[-1].content)
                assert result["provenance"]["source"] == "owner_provided"
                call = ToolCall(
                    id="observed-revision",
                    name="memory_write",
                    arguments={
                        "version": result["version"],
                        "content": result["content"]
                        + "\nAgent observation: verify fresh evidence before relying on past facts.",
                    },
                )
            elif phase == 3:
                call = ToolCall(id="agent-read", name="memory_read", arguments={})
            else:
                result = json.loads(messages[-1].content)
                provenance = result["provenance"]
                assert (
                    provenance["source"] == "agent_authored"
                    and provenance["source_run_id"] == ctx.lease.run_id
                )
                assert (
                    provenance["event_cursor"]
                    and provenance["authority"] == "untrusted_memory_content"
                )
            return ModelReply(
                tool_calls=[call] if call else [],
                text="Memory provenance verified" if not call else "",
            ), ModelSelection(provider="openai", model="scripted-memory")

        with patch.object(ctx.router, "complete", complete):
            await execute_run(ctx, load_tools(), 120, 8)
        assert phase == 4
        print(
            "PASS owner-provided and Agent-authored revisions have actual Run/event provenance; legacy unknown remains unknown and no content grants authority"
        )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
