"""Owner-authenticated exact-version denials and checkpoint instruction binding."""

import asyncio
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.context.skills import (
    assert_skill_authority,
    read_skill_context,
    selected_skill_ids,
)
from lonora_agent.tool_loop import execute_tool_loop, persist
from lonora_api.middleware.auth import require_owner
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import Contract, utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.skills import (
    MAX_SKILL_REVOCATIONS,
    SkillVersionControls,
    SkillVersionRevocation,
)
from lonora_core.user_error import LonoraError
from lonora_db.schema import AgentRow, EventRow, RunRow, SettingRow, TradingJournalRow
from lonora_db.skill_controls import control_key
from lonora_db.transactions import SettingsRepository
from lonora_tools.base import Tool
from lonora_tools.loader import load_tools
from sqlalchemy import func, select


async def main() -> None:
    f = await Fixture().open()
    try:
        agent = await f.agent("Version controls")
        thread = await f.conversation(agent)
        name = "revocable-" + uuid4().hex[:10]
        payload: dict[str, Any] = {
            "name": name,
            "content": "Pinned approved version one.",
            "manifest": {
                "id": name,
                "version": "1.0.0",
                "source": "owner",
                "title": name,
                "description": "Revocation verification",
                "activation": {"mode": "explicit"},
            },
        }
        saved = await f.request("POST", "/skills", {"agent_id": agent["id"], "payload": payload})
        run = await f.request(
            "POST",
            "/runs",
            {
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "prompt": "Use the approved instructions",
                "metadata": {"requested_skills": [name]},
            },
        )
        context = await f.lease(run)
        registry = load_tools()

        async def read(ctx: Any) -> str:
            async with ctx.db.sessions() as session:
                actual = await session.get(AgentRow, ctx.agent_id)
                assert actual is not None
                return await read_skill_context(session, ctx, actual, registry)

        original = await read(context)
        assert "Pinned approved version one" in original
        calls = 0

        async def effect(*args: Any) -> dict[str, Any]:
            nonlocal calls
            calls += 1
            return {"done": True}

        registry.tools["script_effect"] = Tool(
            "script_effect", "Scripted effect only", Contract, effect
        )
        pending = ToolCall(id="proposed-before-revocation", name="script_effect", arguments={})
        await persist(
            context,
            {
                "environment": {"version": 1},
                "instruction_skill_ids": await selected_skill_ids(context),
            },
            [
                ModelMessage(role="system", content=original),
                ModelMessage(role="assistant", content="", tool_calls=[pending]),
            ],
            [pending],
        )
        # Current catalog can advance while the old Run retains its precise instructions.
        new_payload = {
            **payload,
            "content": "Approved new version two.",
            "manifest": {**payload["manifest"], "version": "2.0.0"},
        }
        saved = await f.request(
            "PUT", "/skills/" + saved["id"], {"version": saved["version"], "payload": new_payload}
        )
        endpoint = f"/agents/{agent['id']}/skills/revocations"
        control = await f.request("GET", endpoint)
        assert control["revision"] == 0 and control["revoked"] == []
        body = {
            "skill_id": name,
            "version": "1.0.0",
            "expected_revision": 0,
            "reason": "regression",
        }
        revoked = await f.request("POST", endpoint, body)
        assert revoked["revision"] == 1
        assert revoked == await f.request("POST", endpoint, body)
        # A context refresh may commit new diagnostics and then die before the
        # corresponding messages are checkpointed. Saved instruction IDs still win.
        refreshed = await read(context)
        assert (
            "Pinned approved version one" not in refreshed
            and "Approved new version two" not in refreshed
        )
        recovered = await f.lease(run)

        async def blocked(ctx: Any) -> None:
            with patch(
                "lonora_agent.tool_loop.model_turn",
                side_effect=AssertionError("No model with revoked instructions"),
            ):
                try:
                    await execute_tool_loop(ctx, registry, 8)
                except LonoraError as error:
                    assert error.code == "skill_continuation_unavailable"
                else:
                    raise AssertionError("Revoked pinned checkpoint executed")

        await blocked(recovered)
        assert calls == 0
        async with recovered.db.sessions() as session:
            row = await session.get(RunRow, run["id"])
            assert row is not None
            assert row.execution_state["pending"][0]["id"] == pending.id
            assert (
                row.model_metadata["skill_authority"]["rejected_skills"][name]
                == "skill_version_revoked"
            )
        # Removing/reinstalling and changing a source label cannot erase a denial.
        await f.request("DELETE", "/skills/" + saved["id"])
        saved = await f.request(
            "POST",
            "/skills",
            {
                "agent_id": agent["id"],
                "payload": {
                    **payload,
                    "content": "Same version rewritten.",
                    "manifest": {**payload["manifest"], "source": "external"},
                },
            },
        )
        await blocked(recovered)
        await f.request("DELETE", "/skills/" + saved["id"])
        await f.request("POST", "/skills", {"agent_id": agent["id"], "payload": new_payload})
        # A fresh Run uses unrevoked v2; revoking an unused historical v1 does not block it.
        next_thread = await f.request("POST", "/threads", {"agent_id": agent["id"]})
        next_run = await f.request(
            "POST",
            "/runs",
            {
                "agent_id": agent["id"],
                "thread_id": next_thread["id"],
                "prompt": "Use new version",
                "metadata": {"requested_skills": [name]},
            },
        )
        next_context = await f.lease(next_run)
        block = await read(next_context)
        assert "Approved new version two" in block
        await assert_skill_authority(next_context, registry)
        other = await f.agent("Other Agent")
        assert (await f.request("GET", f"/agents/{other['id']}/skills/revocations"))[
            "revision"
        ] == 0
        # Owner isolation is checked by the authenticated route before any settings read/write.
        f.app.dependency_overrides[require_owner] = lambda: OwnerIdentity(
            id=str(uuid4()), email="foreign@example.test", token_hash="test"
        )
        try:
            assert (await f.client.get("/api" + endpoint)).status_code == 404
            assert (await f.client.post("/api" + endpoint, json=body)).status_code == 404
        finally:
            f.app.dependency_overrides.pop(require_owner)
        # Distinct concurrent updates cannot overwrite each other; exact duplicate is idempotent.
        responses = await asyncio.gather(
            *[
                f.client.post(
                    "/api" + endpoint,
                    json={"skill_id": name, "version": version, "expected_revision": 1},
                )
                for version in ("3.0.0", "4.0.0")
            ]
        )
        assert sorted(response.status_code for response in responses) == [200, 409]
        controls = await f.request("GET", endpoint)
        assert controls["revision"] == 2 and len(controls["revoked"]) == 2
        async with context.db.sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(EventRow)
                    .where(
                        EventRow.owner_id == f.owner,
                        EventRow.agent_id == agent["id"],
                        EventRow.kind == "skill.version_revoked",
                    )
                )
                == 2
            )
            assert await session.scalar(select(func.count()).select_from(TradingJournalRow)) == 0
        # Revoking a dependency blocks its parent, not unrelated active v2 work.
        dependency = name + "-dep"
        parent = name + "-parent"
        for identity, dependencies in ((dependency, []), (parent, [dependency])):
            await f.request(
                "POST",
                "/skills",
                {
                    "agent_id": agent["id"],
                    "payload": {
                        "name": identity,
                        "content": "DEPENDENT PROCEDURE " + identity,
                        "manifest": {
                            **payload["manifest"],
                            "id": identity,
                            "dependencies": dependencies,
                        },
                    },
                },
            )
        await f.request(
            "POST", endpoint, {"skill_id": dependency, "version": "1.0.0", "expected_revision": 2}
        )
        dependency_thread = await f.request("POST", "/threads", {"agent_id": agent["id"]})
        dependency_run = await f.request(
            "POST",
            "/runs",
            {
                "agent_id": agent["id"],
                "thread_id": dependency_thread["id"],
                "prompt": "Use dependent procedure",
                "metadata": {"requested_skills": [parent]},
            },
        )
        dependency_context = await f.lease(dependency_run)
        assert "DEPENDENT PROCEDURE" not in await read(dependency_context)
        async with context.db.sessions() as session:
            row = await session.get(RunRow, dependency_run["id"])
            assert row is not None
            rejected = row.model_metadata["skill_selection"]["rejected_skills"]
            assert rejected[dependency] == "skill_version_revoked"
            assert rejected[parent] == "skill_dependency_unavailable"
        await assert_skill_authority(next_context, registry)
        # New checkpoints bind their actual instructions, not every older snapshot entry.
        async with context.db.sessions() as session, session.begin():
            row = await session.get(RunRow, next_run["id"])
            assert row is not None
            snapshot = row.model_metadata["skill_snapshot"]
            row.model_metadata = {
                **row.model_metadata,
                "skill_snapshot": {
                    **snapshot,
                    "skills": {
                        **snapshot["skills"],
                        dependency: {
                            "manifest": {**payload["manifest"], "id": dependency},
                            "content": "Unused revoked old instructions.",
                        },
                    },
                },
            }

        async def complete_new(*args: Any, **kwargs: Any) -> tuple[ModelReply, ModelSelection]:
            assert "Approved new version two" in args[1][0].content
            assert "Unused revoked old instructions" not in args[1][0].content
            return ModelReply(text="Completed with unrevoked instructions"), ModelSelection(
                provider="openai", model="scripted"
            )

        with patch("lonora_agent.tool_loop.model_turn", complete_new):
            outcome = await execute_tool_loop(next_context, registry, 8)
        assert outcome.text.startswith("Completed")
        async with context.db.sessions() as session:
            row = await session.get(RunRow, next_run["id"])
            assert row is not None
            assert row.execution_state["instruction_skill_ids"] == [name]
        forged = await f.client.post("/api" + endpoint, json={**body, "owner_id": "forged"})
        assert forged.status_code == 422
        # Bounded controls reject overflow without dropping an earlier denial.
        bounded = SkillVersionControls(
            owner_id=f.owner,
            agent_id=other["id"],
            revision=MAX_SKILL_REVOCATIONS,
            revoked=[
                SkillVersionRevocation(
                    skill_id="limits", version=f"{index}.0.0", revoked_at=utcnow()
                )
                for index in range(MAX_SKILL_REVOCATIONS)
            ],
        )
        async with context.db.sessions() as session, session.begin():
            await SettingsRepository().put(
                session, control_key(f.owner, other["id"]), bounded.model_dump(mode="json")
            )
        other_endpoint = f"/agents/{other['id']}/skills/revocations"
        overflow = await f.client.post(
            "/api" + other_endpoint,
            json={
                "skill_id": "limits",
                "version": "999.0.0",
                "expected_revision": MAX_SKILL_REVOCATIONS,
            },
        )
        assert overflow.status_code == 409 and overflow.json()["code"] == "skill_revocation_limit"
        assert (await f.request("GET", other_endpoint))["revision"] == MAX_SKILL_REVOCATIONS
        await f.request("DELETE", "/agents/" + other["id"])
        f.agents.remove(other["id"])
        async with context.db.sessions() as session:
            assert await session.get(SettingRow, control_key(f.owner, other["id"])) is None
        try:
            await assert_skill_authority(context, registry)
        except LonoraError as error:
            assert error.code == "stale_lease"
        else:
            raise AssertionError("Stale worker passed")
        print(
            "PASS exact pinned revocation, checkpoint/metadata crash boundary, authenticated owner/Agent isolation, newer version, source/delete/reinstall denial, optimistic concurrency and one durable event per denial"
        )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
