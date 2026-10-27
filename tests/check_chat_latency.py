"""Real PostgreSQL checks: optional history work follows committed replies."""

import asyncio
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelReply
from lonora_agent.executor import execute_run
from lonora_agent.progress import progress
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_db.memory import commit_memory, memory_provenance
from lonora_db.schema import MessageRow, RunRow, ThreadRow
from lonora_gateway.history_maintenance import maintain_history
from lonora_tools.loader import load_tools
from sqlalchemy import select


async def main() -> None:
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Post-reply history")
        thread = await fixture.conversation(agent)
        async with fixture.runtime.db.sessions() as session, session.begin():
            stored = await session.get(ThreadRow, thread["id"])
            assert stored
            for seq in range(1, 82):
                session.add(
                    MessageRow(
                        thread_id=stored.id,
                        seq=seq,
                        role="user" if seq % 2 else "assistant",
                        content=f"Historical observation {seq}",
                        agent_id=None if seq % 2 else agent["id"],
                    )
                )
            stored.next_seq = 82
            legacy = await memory_provenance(session, agent["id"], 1)
            assert legacy["source"] == "legacy_unknown"
            await commit_memory(session, fixture.owner, agent["id"], "Prefer concise replies", 1)
        async with fixture.runtime.db.sessions() as session:
            source = await memory_provenance(session, agent["id"], 2)
            assert source["source"] == "owner_provided"

        context = await fixture.lease(await fixture.run(agent, thread))
        await progress(context, "tool.started", {"call_id": "search", "name": "web_search"})
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(RunRow, context.lease.run_id)
            assert row and row.model_metadata["activity"]["kind"] == "tool.started"
            assert row.model_metadata["activity"]["name"] == "web_search"
        await progress(context, "tool.completed", {"call_id": "search", "name": "web_search"})

        background_started = asyncio.Event()
        allow_summary = asyncio.Event()
        calls: list[Capability] = []

        async def complete(capability: Capability, messages: Any, tools: Any, **kwargs: Any):
            calls.append(capability)
            if capability == Capability.BACKGROUND:
                assert "Later owner message" not in str(messages)
                background_started.set()
                await allow_summary.wait()
                answer = "Prior historical observations, without current market authority."
            else:
                answer = "The reply is ready."
            return ModelReply(text=answer), ModelSelection(
                provider="openai", model="scripted-latency-check"
            )

        with patch.object(context.router, "complete", complete):
            await execute_run(context, load_tools(), 120, 4)
            assert calls == [Capability.CONVERSATION]
            maintenance = asyncio.create_task(
                maintain_history(
                    fixture.runtime.services(fixture.owner), fixture.settings.artifact_root
                )
            )
            try:
                await asyncio.wait_for(background_started.wait(), timeout=15)
                async with fixture.runtime.db.sessions() as session:
                    row = await session.get(RunRow, context.lease.run_id)
                    stored = await session.get(ThreadRow, thread["id"])
                    assert row and row.status == "completed" and row.result == "The reply is ready."
                    assert stored and stored.summary_seq == 0
                    answer = await session.scalar(
                        select(MessageRow).where(
                            MessageRow.thread_id == stored.id,
                            MessageRow.content == "The reply is ready.",
                        )
                    )
                    assert answer
                await fixture.request(
                    "POST",
                    f"/threads/{thread['id']}/messages",
                    {"content": "Later owner message", "client_nonce": "later-owner-message"},
                )
                allow_summary.set()
                await asyncio.wait_for(maintenance, timeout=15)
                async with fixture.runtime.db.sessions() as session:
                    stored = await session.get(ThreadRow, thread["id"])
                    assert stored and 0 < stored.summary_seq < 81
                    assert stored.context_summary.startswith("Prior historical observations")
            finally:
                allow_summary.set()
                maintenance.cancel()
                await asyncio.gather(maintenance, return_exceptions=True)
        print(
            "PASS indexed memory provenance; durable actual activity; reply and new Send remain available while summary is blocked; frozen cutoff excludes later owner messages"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
