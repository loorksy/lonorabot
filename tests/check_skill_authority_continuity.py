"""PostgreSQL same-Run withdrawal boundaries; scripted effects only."""

import asyncio
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.context.skills import assert_skill_authority, read_skill_context
from lonora_agent.environment import route_key
from lonora_agent.tool_loop import execute_tool_loop, persist
from lonora_contracts.domain import Contract
from lonora_contracts.model_routing import ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.schema import AgentRow, RunRow, SkillRow
from lonora_tools.base import Tool
from lonora_tools.loader import load_tools
from lonora_tools.registry import ToolRegistry


async def main() -> None:
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Skill authority continuity")
        thread = await fixture.conversation(agent)
        name = "continuity-" + uuid4().hex[:10]
        payload: dict[str, Any] = {
            "name": name,
            "content": "Pinned version one instructions.",
            "manifest": {
                "id": name,
                "version": "1.0.0",
                "title": name,
                "description": "Authority continuity verification",
                "source": "owner",
                "activation": {"mode": "explicit"},
            },
        }
        saved = await fixture.request(
            "POST", "/skills", {"agent_id": agent["id"], "payload": payload}
        )
        run = await fixture.request(
            "POST",
            "/runs",
            {
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "prompt": "Use the installed instructions",
                "metadata": {"requested_skills": [name]},
            },
        )
        context = await fixture.lease(run)
        writes: list[str] = []

        async def catalog(**changes: Any) -> None:
            async with context.db.sessions() as session, session.begin():
                row = await session.get(SkillRow, saved["id"])
                assert row is not None
                row.payload = {**row.payload, **changes}

        async def first(*args: Any) -> dict[str, Any]:
            writes.append("first")
            await catalog(enabled=False)
            return {"done": "first"}

        async def second(*args: Any) -> dict[str, Any]:
            writes.append("second")
            return {"done": "second"}

        registry = ToolRegistry(
            [
                *[tool for tool in load_tools().tools.values() if tool.name != "tool_environment"],
                Tool("script_first", "Scripted effect", Contract, first),
                Tool("script_second", "Scripted effect", Contract, second),
            ]
        )
        async with context.db.sessions() as session:
            stored_agent = await session.get(AgentRow, agent["id"])
            assert stored_agent is not None
            block = await read_skill_context(session, context, stored_agent, registry)
        assert "Pinned version one" in block
        async with context.db.sessions() as session:
            stored = await session.get(RunRow, run["id"])
            assert stored is not None
            original_snapshot = stored.model_metadata["skill_snapshot"]
        calls = [
            ToolCall(id="first", name="script_first", arguments={}),
            ToolCall(id="second", name="script_second", arguments={}),
        ]
        await persist(
            context,
            {"environment": {"version": 1}},
            [
                ModelMessage(role="system", content=block),
                ModelMessage(role="user", content="Perform the two scripted steps"),
                ModelMessage(role="assistant", content="", tool_calls=calls),
            ],
            calls,
        )

        async def blocked(ctx: Any) -> None:
            try:
                await execute_tool_loop(ctx, registry, 5)
            except LonoraError as error:
                assert error.code == "skill_continuation_unavailable"
            else:
                raise AssertionError("Withdrawn instructions continued")

        with patch(
            "lonora_agent.tool_loop.model_turn",
            side_effect=AssertionError("No model after withdrawal"),
        ):
            await blocked(context)
        assert writes == ["first"]
        async with context.db.sessions() as session:
            stored = await session.get(RunRow, run["id"])
            assert stored is not None
            assert [item["id"] for item in stored.execution_state["pending"]] == ["second"]
            assert stored.model_metadata["skill_snapshot"] == original_snapshot
            assert (
                stored.model_metadata["skill_authority"]["rejected_skills"][name]
                == "skill_disabled"
            )
        # A new worker cannot bypass withdrawal by restoring the checkpoint without steering.
        recovered = await fixture.lease(run)
        await blocked(recovered)
        assert writes == ["first"]
        try:
            await assert_skill_authority(context, registry)
        except LonoraError as error:
            assert error.code == "stale_lease"
        else:
            raise AssertionError("Stale worker passed authority check")
        # Current source changes and removal are authoritative as well.
        await catalog(enabled=True, manifest={**payload["manifest"], "source": "external"})
        await blocked(recovered)
        assert writes == ["first"]
        async with context.db.sessions() as session, session.begin():
            row = await session.get(SkillRow, saved["id"])
            assert row is not None
            await session.delete(row)
        await blocked(recovered)
        # Reinstalling allowed newer same-source catalog content does not upgrade this Run.
        await fixture.request(
            "POST",
            "/skills",
            {
                "agent_id": agent["id"],
                "payload": {
                    **payload,
                    "content": "New version two instructions.",
                    "manifest": {**payload["manifest"], "version": "2.0.0"},
                },
            },
        )

        async def model(*args: Any, **kwargs: Any) -> tuple[ModelReply, ModelSelection]:
            assert "Pinned version one" in args[1][0].content
            assert "New version two" not in args[1][0].content
            return ModelReply(text="Completed"), ModelSelection(provider="openai", model="scripted")

        with patch("lonora_agent.tool_loop.model_turn", model):
            outcome = await execute_tool_loop(recovered, registry, 5)
        assert outcome.text == "Completed" and writes == ["first", "second"]
        # Model boundary is checked even when no effects remain.
        async with recovered.db.sessions() as session, session.begin():
            from sqlalchemy import select

            row = await session.scalar(
                select(SkillRow).where(
                    SkillRow.agent_id == agent["id"], SkillRow.payload["name"].as_string() == name
                )
            )
            assert row is not None
            row.payload = {**row.payload, "enabled": False}
        with patch(
            "lonora_agent.tool_loop.model_turn", side_effect=AssertionError("No stale model turn")
        ):
            await blocked(recovered)
        # Known ambiguous financial recovery retains its SAME original operation
        # before any new model/effect is admitted. This handler is scripted, not a broker.
        reconciled: list[str] = []

        async def reconcile(ctx: Any, args: Any) -> dict[str, Any]:
            reconciled.append(ctx.call_id)
            return {"status": "confirmed", "operation_id": "existing-operation"}

        registry.tools["script_reconcile"] = Tool(
            "script_reconcile",
            "Scripted same-operation recovery",
            Contract,
            reconcile,
            financial=True,
            replay_safe=True,
        )
        replay = ToolCall(id="invented-recovery-id", name="script_reconcile", arguments={})
        await persist(
            recovered,
            {
                "environment": {
                    "version": 1,
                    "routes": {
                        route_key(replay): {
                            "ambiguous": True,
                            "receipt_replay": True,
                            "origin_call_id": "original-operation-call",
                        },
                    },
                }
            },
            [
                ModelMessage(role="system", content=block),
                ModelMessage(role="assistant", content="", tool_calls=[replay]),
            ],
            [replay],
        )
        await blocked(recovered)
        assert reconciled == ["original-operation-call"]
        assert writes == ["first", "second"]
        print(
            "PASS Skill withdrawal between effects, restored checkpoints, model boundary, source/removal, retained pending IDs/snapshot, re-enable and stale fence"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
