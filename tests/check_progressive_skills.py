"""Real PostgreSQL progressive discovery, immutable replay and authority checkpoints.

Run through .runtime/spec-test.py with a disposable *_test database. Models and
nonfinancial effects are scripted; no external model or broker is contacted.
"""

import asyncio
import json
from dataclasses import replace
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.skills.access import RunSkillAccess, admitted_view_ids, view_key
from lonora_agent.tool_loop import execute_tool_loop
from lonora_contracts.domain import Contract
from lonora_contracts.model_routing import ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.schema import EffectReceiptRow, RunRow, SkillRow
from lonora_tools.base import Tool
from lonora_tools.loader import load_tools
from lonora_tools.registry import ToolRegistry
from sqlalchemy import func, select


class WorkerDeath(BaseException):
    pass


async def expect_code(code: str, operation: Any) -> None:
    try:
        await operation
    except LonoraError as error:
        assert error.code == code, (error.code, code)
    else:
        raise AssertionError("Expected " + code)


async def main() -> None:
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Progressive Skills")
        thread = await fixture.conversation(agent)
        identity = "overnight-procedure"
        content = "Compare yesterday's broker observations with today's exact evidence."
        payload: dict[str, Any] = {
            "name": identity,
            "content": content,
            "manifest": {
                "id": identity,
                "version": "1.0.0",
                "title": "Overnight observations",
                "description": "Compare observations from consecutive sessions.",
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
                "prompt": "Compare the overnight observations using a suitable procedure.",
            },
        )
        context = await fixture.lease(run)
        registry = load_tools()
        listed = ToolCall(id="catalog", name="skills_list", arguments={"limit": 20})
        viewed = ToolCall(id="view", name="skill_view", arguments={"skill_id": identity})
        phase = 0

        async def model(
            ctx: Any, messages: list[ModelMessage], *args: Any
        ) -> tuple[ModelReply, ModelSelection]:
            nonlocal phase
            phase += 1
            if phase == 1:
                assert content not in messages[0].content
                assert "skills_list" in messages[0].content
                reply = ModelReply(text="", tool_calls=[listed])
            elif phase == 2:
                catalog = json.loads(messages[-1].content)
                entry = next(item for item in catalog["skills"] if item["id"] == identity)
                assert entry["available"] and "content" not in entry
                assert catalog["authority_granted"] is False
                reply = ModelReply(text="", tool_calls=[viewed])
            else:
                result = json.loads(messages[-1].content)
                assert result["skills"][0]["content"] == content
                assert result["skills"][0]["version"] == "1.0.0"
                async with ctx.db.sessions() as session:
                    stored = await session.get(RunRow, run["id"])
                    assert stored is not None
                    assert identity in stored.execution_state["instruction_skill_ids"]
                    assert identity in stored.execution_state["viewed_skill_ids"]
                reply = ModelReply(text="Compared using the selected procedure.")
            return reply, ModelSelection(provider="openai", model="scripted")

        # Death occurs after the view's transaction commits, before ToolLoop sees its result.
        real_view = RunSkillAccess.view

        async def die_after_view(self: Any, ctx: Any, skill_id: str) -> dict[str, Any]:
            await real_view(self, ctx, skill_id)
            raise WorkerDeath()

        with (
            patch("lonora_agent.tool_loop.model_turn", model),
            patch.object(RunSkillAccess, "view", die_after_view),
        ):
            try:
                await execute_tool_loop(context, registry, 6)
            except WorkerDeath:
                pass
            else:
                raise AssertionError("Worker did not die at the intended boundary")
        assert phase == 2
        async with context.db.sessions() as session:
            stored = await session.get(RunRow, run["id"])
            assert stored is not None
            assert identity not in stored.execution_state["instruction_skill_ids"]
            assert stored.execution_state["pending"][0]["id"] == "view"
            assert identity in stored.model_metadata["skill_snapshot"]["skills"]
        async with context.db.sessions() as session, session.begin():
            row = await session.get(SkillRow, saved["id"])
            assert row is not None
            row.payload = {
                **row.payload,
                "content": "Changed version two procedure must not replace this Run.",
                "manifest": {**payload["manifest"], "version": "2.0.0"},
            }
        recovered = await fixture.lease(run)
        with patch("lonora_agent.tool_loop.model_turn", model):
            outcome = await execute_tool_loop(recovered, registry, 6)
        assert "Compared" in outcome.text and phase == 3
        async with context.db.sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(EffectReceiptRow)
                    .where(EffectReceiptRow.key == view_key(recovered.for_call("view")))
                )
                == 1
            )
        access = RunSkillAccess(registry, (identity,))
        page = await access.catalog(recovered.for_call("page"), 0, 1)
        assert len(page["skills"]) == 1 and page["next_offset"] == 1
        assert "content" not in page["skills"][0]
        assert page["total"] > 1
        ack = await access.view(recovered.for_call("view"), identity)
        assert ack["skills"][0]["content"] == content
        await expect_code(
            "skill_view_identity_conflict",
            access.view(recovered.for_call("view"), "memory"),
        )
        await expect_code("stale_lease", access.view(context.for_call("view"), identity))
        await expect_code(
            "skill_scope_mismatch",
            access.view(replace(recovered, owner_id="other-owner").for_call("view"), identity),
        )
        forged = {"ok": True, **ack, "skills": [{**ack["skills"][0], "content": "forged"}]}
        await expect_code(
            "skill_view_identity_conflict",
            admitted_view_ids(recovered, registry, viewed, forged, [identity]),
        )
        # A newly relevant automatic Skill cannot displace/conflict with the retained view.
        await fixture.request(
            "POST",
            "/skills",
            {
                "agent_id": agent["id"],
                "payload": {
                    "name": "conflicting-automatic",
                    "content": "Conflicting automatic instructions.",
                    "manifest": {
                        "id": "conflicting-automatic",
                        "version": "1.0.0",
                        "title": "Conflicting automatic",
                        "description": "Scripted conflict",
                        "source": "owner",
                        "priority": 100,
                        "activation": {"mode": "automatic", "intents": ["market"]},
                        "conflicts": [identity],
                    },
                },
            },
        )
        # Steering replaces automatic system selection, but the prior viewed exchange remains.
        steered = False

        async def steering(ctx: Any, state: Any, messages: list[ModelMessage]) -> bool:
            nonlocal steered
            if steered:
                return False
            steered = True
            messages.append(
                ModelMessage(
                    role="user", content="Analyze the observations using the prior procedure."
                )
            )
            return True

        async def after_steering(ctx: Any, messages: list[ModelMessage], *args: Any) -> Any:
            assert any(content in message.content for message in messages)
            assert "Conflicting automatic instructions" not in messages[0].content
            return ModelReply(text="Continued"), ModelSelection(provider="openai", model="scripted")

        with (
            patch("lonora_agent.tool_loop.merge_steering", steering),
            patch("lonora_agent.tool_loop.model_turn", after_steering),
        ):
            await execute_tool_loop(recovered, registry, 8)
        async with recovered.db.sessions() as session:
            stored = await session.get(RunRow, run["id"])
            assert stored is not None
            assert identity in stored.execution_state["instruction_skill_ids"]
        # Exact pinned version revocation prevents both re-reading and continuing to reason.
        await fixture.request(
            "POST",
            f"/agents/{agent['id']}/skills/revocations",
            {"skill_id": identity, "version": "1.0.0", "expected_revision": 0},
        )
        await expect_code(
            "skill_version_revoked", access.view(recovered.for_call("view"), identity)
        )
        denied_catalog = await access.catalog(recovered.for_call("denied-page"), 0, 20)
        denied = next(item for item in denied_catalog["skills"] if item["id"] == identity)
        assert denied["version"] == "1.0.0" and denied["code"] == "skill_version_revoked"
        assert denied["available"] is False
        with patch("lonora_agent.tool_loop.model_turn", side_effect=AssertionError("No model")):
            await expect_code(
                "skill_continuation_unavailable", execute_tool_loop(recovered, registry, 8)
            )
        # Fresh Run reads unrevoked v2 while prior v1 remains permanently blocked.
        fresh = await fixture.run(agent, thread)
        fresh_context = await fixture.lease(fresh)
        fresh_view = await RunSkillAccess(registry, ()).view(
            fresh_context.for_call("fresh-view"), identity
        )
        assert fresh_view["skills"][0]["version"] == "2.0.0"
        assert fresh_view["skills"][0]["content"] != content
        await pending_effect_guard(fixture, agent, thread, identity)
        print("Progressive Skills PostgreSQL checks passed")
    finally:
        await fixture.close()


async def pending_effect_guard(
    fixture: Fixture, agent: dict[str, Any], thread: dict[str, Any], identity: str
) -> None:
    """A view and later effect in one assistant exchange obey the new binding."""
    from lonora_agent.tool_loop import persist as real_persist

    run = await fixture.run(agent, thread)
    context = await fixture.lease(run)
    effects: list[str] = []

    async def effect(*args: Any) -> dict[str, Any]:
        effects.append("unexpected")
        return {"done": True}

    registry = ToolRegistry(
        [
            *[tool for tool in load_tools().tools.values() if tool.name != "tool_environment"],
            Tool("script_effect", "Scripted nonfinancial effect", Contract, effect),
        ]
    )
    calls = [
        ToolCall(id="admit", name="skill_view", arguments={"skill_id": identity}),
        ToolCall(id="effect", name="script_effect", arguments={}),
    ]

    async def model(*args: Any) -> Any:
        return ModelReply(text="", tool_calls=calls), ModelSelection(
            provider="openai", model="scripted"
        )

    async def withdraw_after_checkpoint(ctx: Any, state: Any, messages: Any, pending: Any) -> None:
        await real_persist(ctx, state, messages, pending)
        if state.get("viewed_skill_ids") == [identity]:
            async with ctx.db.sessions() as session, session.begin():
                rows = (
                    await session.scalars(select(SkillRow).where(SkillRow.agent_id == agent["id"]))
                ).all()
                for row in rows:
                    if row.payload["name"] == identity:
                        row.payload = {**row.payload, "enabled": False}

    with (
        patch("lonora_agent.tool_loop.model_turn", model),
        patch("lonora_agent.tool_loop.persist", withdraw_after_checkpoint),
    ):
        await expect_code("skill_continuation_unavailable", execute_tool_loop(context, registry, 4))
    assert effects == []
    async with context.db.sessions() as session:
        stored = await session.get(RunRow, run["id"])
        assert stored is not None
        assert [call["id"] for call in stored.execution_state["pending"]] == ["effect"]
        assert stored.execution_state["messages"][-1]["tool_call_id"] == "admit"
    recovered = await fixture.lease(run)
    await expect_code("skill_continuation_unavailable", execute_tool_loop(recovered, registry, 4))
    assert effects == []


if __name__ == "__main__":
    asyncio.run(main())
