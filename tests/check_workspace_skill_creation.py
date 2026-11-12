"""Agent-created analytical packages: source from a directory of the owner's persistent
workspace (7.1), files kept in the agent's private package store, utilities validated in
the workspace from a copy, existing lifecycle and fences. The supervisor is a stand-in."""

import asyncio
import hashlib
import json
from dataclasses import replace
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.context.skills import assert_skill_authority
from lonora_agent.executor import execute_run
from lonora_agent.skills.access import RunSkillAccess
from lonora_agent.skills.store import store_files, stored_files
from lonora_contracts.model_routing import ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.schema import EffectReceiptRow, RunRow, SkillRow, TradeApprovalRow, TradingJournalRow
from lonora_db.skills import SkillRepository
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from sqlalchemy import func, select
from workspace_fake import FakeWorkspace, Ran

DOCUMENT = "---\nname: local-statistics\ndescription: Calculate bounded historical dispersion using verified exact-symbol observations.\n---\nPreserve exact broker symbols and observation timestamps. Analytical statistics grant no trading authority.\n"
SOURCE = "import statistics\nassert statistics.mean([1, 2, 3]) == 2\nprint('mean=2')\n"
REVIEW = {
    "source_behavior": "Compute descriptive statistics on a bounded supplied historical fixture.",
    "adapted_behavior": "Reuse the same analytical helper with exact owner-provided symbol observations.",
    "assumptions": ["Caller verifies observations and timestamps through existing market readers."],
    "limitations": [
        "Passing a smoke test does not establish predictive quality, strategy equivalence or financial authority."
    ],
}
UTILITY = "skills/local-statistics/1.0.0/stats.py"


async def denied(awaitable: Any, code: str) -> None:
    try:
        await awaitable
    except LonoraError as error:
        assert error.code == code, (error.code, code)
    else:
        raise AssertionError("Expected refusal " + code)


async def main() -> None:
    fixture = await Fixture().open()
    registry = load_tools()

    def python(agent_id: str, command: str) -> Ran:
        # A fresh copy of the stored files is in place before the utility runs.
        assert command == f"python3 {UTILITY}", command
        assert workspace.files[(agent_id, UTILITY)] == SOURCE.encode()
        return {"exit_code": 0, "stdout": "mean=2\n"}

    workspace = FakeWorkspace(python)
    try:
        agent = await fixture.agent("Local analytical packages")
        thread = await fixture.conversation(agent)
        draft = "drafts/statistics"
        workspace.files[(agent["id"], f"{draft}/SKILL.md")] = DOCUMENT.encode()
        workspace.files[(agent["id"], f"{draft}/stats.py")] = SOURCE.encode()

        async def fresh() -> ToolContext:
            return replace(
                await fixture.lease(await fixture.run(agent, thread)),
                workspace=workspace.client(),
                skill_access=RunSkillAccess(registry, ()),
            )

        context = await fresh()
        results: list[dict[str, Any]] = []
        rounds = 0

        async def model(
            _capability: Any, messages: list[ModelMessage], _tools: Any, **_kwargs: Any
        ):
            nonlocal rounds
            rounds += 1
            if rounds > 1:
                expected_call = ("create-local", "test-local", "activate-local", "read-local")[
                    rounds - 2
                ]
                observation = next(
                    message
                    for message in messages
                    if message.role == "tool" and message.tool_call_id == expected_call
                )
                result = json.loads(observation.content)
                assert result["ok"], result
                results.append(result)
            if rounds == 1:
                call = ToolCall(
                    id="create-local",
                    name="skill_package_create",
                    arguments={
                        "source_directory": draft,
                        "version": "1.0.0",
                        "expected_version": 0,
                        "adapted_content": DOCUMENT,
                        "review": REVIEW,
                    },
                )
            elif rounds == 2:
                created = results[-1]
                assert created["source_kind"] == "workspace" and not created["enabled"]
                assert (
                    created["commit"]
                    is created["archive_sha256"]
                    is created["repository_url"]
                    is None
                )
                row = await fixture.request("GET", "/skills/" + created["resource_id"])
                bypass = await fixture.client.put(
                    "/api/skills/" + row["id"],
                    json={
                        "version": row["version"],
                        "payload": {**row["payload"], "enabled": True},
                    },
                )
                assert (
                    bypass.status_code == 409
                    and bypass.json()["code"] == "skill_package_lifecycle_required"
                )
                call = ToolCall(
                    id="test-local",
                    name="skill_package_validate",
                    arguments={
                        "skill_id": "local-statistics",
                        "expected_version": created["resource_version"],
                        "utility_path": UTILITY,
                    },
                )
            elif rounds == 3:
                assert results[-1]["exit_code"] == 0 and "mean=2" in results[-1]["stdout"]
                assert results[-1]["validation_level"] == "workspace_smoke_test"
                call = ToolCall(
                    id="activate-local",
                    name="skill_package_control",
                    arguments={
                        "skill_id": "local-statistics",
                        "expected_version": results[-1]["resource_version"],
                        "action": "activate",
                    },
                )
            elif rounds == 4:
                call = ToolCall(
                    id="read-local", name="skill_view", arguments={"skill_id": "local-statistics"}
                )
            else:
                assert "observation timestamps" in results[-1]["skills"][0]["content"]
                return ModelReply(
                    text="The historical calculation completed and its reusable procedure is available."
                ), ModelSelection(provider="openai", model="scripted-local-package")
            return ModelReply(tool_calls=[call]), ModelSelection(
                provider="openai", model="scripted-local-package"
            )

        async with context.db.sessions() as session:
            journals = await session.scalar(select(func.count()).select_from(TradingJournalRow))
            approvals = await session.scalar(select(func.count()).select_from(TradeApprovalRow))
        with patch.object(context.router, "complete", model):
            await execute_run(context, registry, 120, 10)
        async with context.db.sessions() as session:
            run = await session.get(RunRow, context.lease.run_id)
            assert run and run.status == "completed", run.error_code if run else None
            assert "skill_execution_image" not in run.model_metadata
            row = await session.get(SkillRow, results[0]["resource_id"])
            assert row and row.payload["enabled"]
            entry = row.state["package"]["versions"][0]
            assert entry["workspace_source"]["agent_id"] == agent["id"]
            assert entry["workspace_source"]["run_id"] == context.lease.run_id
            assert entry["workspace_source"]["workspace_revision"] is None
            assert set(entry["validation"][UTILITY]) == {
                "source_sha256",
                "exit_code",
                "arguments",
                "validated_at",
            }
            # The package's files are in the agent's private store.
            stored = await stored_files(session, agent["id"])
            assert stored[UTILITY] == SOURCE.encode()
        print(
            "PASS workspace directory -> disabled package in the private store -> utility run in"
            " the workspace from a fresh copy -> activation -> view; no generic enable bypass"
        )

        page = await fixture.request("GET", f"/agents/{agent['id']}/skills/catalog")
        item = next(item for item in page["items"] if item["id"] == "local-statistics")
        assert item["available"], item
        print("PASS the owner's catalog reflects the stored source and the validation")

        context = await fresh()

        async def call(
            identity: str, name: str, arguments: dict[str, Any], ctx: ToolContext | None = None
        ):
            return await registry.execute(
                ToolCall(id=identity, name=name, arguments=arguments), ctx or context
            )

        viewed = await call("later-view", "skill_view", {"skill_id": "local-statistics"})
        assert viewed == await call("later-view", "skill_view", {"skill_id": "local-statistics"})
        await assert_skill_authority(context, registry, active_ids=["local-statistics"])
        print("PASS a later Run reuses the same exact version; a replayed view runs nothing")

        crash_doc = DOCUMENT.replace("local-statistics", "recovered-statistics")
        workspace.files[(agent["id"], "recovery/SKILL.md")] = crash_doc.encode()
        workspace.files[(agent["id"], "recovery/stats.py")] = SOURCE.encode()
        create = {
            "source_directory": "recovery",
            "version": "1.0.0",
            "expected_version": 0,
            "adapted_content": crash_doc,
            "review": REVIEW,
        }
        original_create = SkillRepository.create
        interrupted = False

        async def crash_once(self: SkillRepository, *args: Any, **kwargs: Any):
            nonlocal interrupted
            if not interrupted:
                interrupted = True
                raise RuntimeError("scripted crash before publication")
            return await original_create(self, *args, **kwargs)

        with patch.object(SkillRepository, "create", crash_once):
            try:
                await call("recover-create", "skill_package_create", create)
            except RuntimeError:
                pass
            else:
                raise AssertionError("creation crash was not injected")
            # The source changes after the crash; the retry uses the prepared source.
            workspace.files[(agent["id"], "recovery/stats.py")] = b"print('changed')\n"
            recovered = await call("recover-create", "skill_package_create", create)
        assert not recovered["enabled"]
        assert (
            recovered["files"]["skills/recovered-statistics/1.0.0/stats.py"]
            == hashlib.sha256(SOURCE.encode()).hexdigest()
        )
        assert recovered == await call("recover-create", "skill_package_create", create)
        await denied(
            call("recover-create", "skill_package_create", {**create, "version": "2.0.0"}),
            "skill_package_identity_conflict",
        )
        print(
            "PASS a crash before publication resumes the exact prepared source; the same effect"
            " cannot change its semantic version"
        )

        await denied(
            call(
                "cross-owner",
                "skill_package_create",
                create,
                replace(context, owner_id=str(uuid4())),
            ),
            "agent_not_found",
        )
        other = await fixture.agent("Unrelated local package owner")
        await denied(
            call(
                "cross-agent",
                "skill_package_create",
                create,
                replace(context, agent_id=other["id"]),
            ),
            "workspace_scope_mismatch",
        )
        await denied(
            call("missing-source", "skill_package_create", {**create, "source_directory": "none"}),
            "skill_package_document_missing",
        )
        async with context.db.sessions() as session, session.begin():
            run = await session.get(RunRow, context.lease.run_id)
            assert run
            trigger, run.trigger = run.trigger, "subagent"
        await denied(
            call("helper-create", "skill_package_create", create), "workspace_run_scope_refused"
        )
        async with context.db.sessions() as session, session.begin():
            run = await session.get(RunRow, context.lease.run_id)
            assert run
            run.trigger = trigger
        print("PASS owner/Agent scope, a missing source and helper creation fail closed")

        async with context.db.sessions() as session, session.begin():
            await store_files(session, agent["id"], {UTILITY: "print('changed source')\n"})
        await denied(
            call("tampered-view", "skill_view", {"skill_id": "local-statistics"}),
            "skill_package_source_changed",
        )
        catalog = await call("tampered-list", "skills_list", {"limit": 20})
        assert (
            next(item for item in catalog["skills"] if item["id"] == "local-statistics")["code"]
            == "skill_package_source_changed"
        )
        print("PASS a changed stored source invalidates admission even when enabled")

        async with context.db.sessions() as session:
            assert (
                await session.scalar(select(func.count()).select_from(TradingJournalRow))
                == journals
            )
            assert (
                await session.scalar(select(func.count()).select_from(TradeApprovalRow))
                == approvals
            )
            prepared = (
                await session.scalars(
                    select(EffectReceiptRow).where(EffectReceiptRow.key.endswith(":prepared"))
                )
            ).all()
            assert len(prepared) == 2
        print("PASS financial approvals and journal unchanged")
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
