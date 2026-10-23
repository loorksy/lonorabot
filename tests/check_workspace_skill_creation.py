"""Agent-created analytical packages use existing workspace, lifecycle and fences.

Set LONORA_SKILL_TEST_IMAGE to an already reviewed immutable image ID to run the
initial utility through actual restricted Docker. Default execution is scripted.
"""

import asyncio
import json
import os
from dataclasses import replace
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.context.skills import assert_skill_authority
from lonora_agent.executor import execute_run
from lonora_agent.skills.access import RunSkillAccess
from lonora_agent.workspace import AnalyticalContainer, WorkspaceResult
from lonora_agent.workspace_access import RunWorkspaceAccess
from lonora_agent.workspace_client import WorkspaceClient
from lonora_contracts.model_routing import ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.schema import EffectReceiptRow, RunRow, SkillRow, TradeApprovalRow, TradingJournalRow
from lonora_db.skills import SkillRepository
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from sqlalchemy import func, select

DOCUMENT = "---\nname: local-statistics\ndescription: Calculate bounded historical dispersion using verified exact-symbol observations.\n---\nPreserve exact broker symbols and observation timestamps. Analytical statistics grant no trading authority.\n"
SOURCE = "import json, statistics\nfrom pathlib import Path\nvalues = [1, 2, 3]\nmean = statistics.mean(values)\nassert mean == 2\nPath('local-result.json').write_text(json.dumps({'mean': mean}))\nprint('mean=2')\n"
REVIEW = {
    "source_behavior": "Compute descriptive statistics on a bounded supplied historical fixture.",
    "adapted_behavior": "Reuse the same analytical helper with exact owner-provided symbol observations.",
    "assumptions": ["Caller verifies observations and timestamps through existing market readers."],
    "limitations": [
        "Passing a smoke test does not establish predictive quality, strategy equivalence or financial authority."
    ],
}
IMAGE = "sha256:" + "a" * 64


class ScriptedExecutor:
    def __init__(self) -> None:
        self.image = IMAGE
        self.calls = 0

    async def profile(self) -> str:
        return self.image

    async def execute(
        self,
        command: str,
        files: dict[str, bytes] | None = None,
        *,
        deadline_seconds: float = 30,
        expected_image: str | None = None,
    ) -> WorkspaceResult:
        if expected_image is not None and expected_image != self.image:
            raise LonoraError("workspace_profile_changed", 409)
        self.calls += 1
        assert command.startswith("python3 skills/") and deadline_seconds == 30
        return WorkspaceResult(
            0, "mean=2\n", "", {**(files or {}), "local-result.json": b'{"mean": 2}'}, self.image
        )


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
    fake = ScriptedExecutor()
    real_image = os.environ.get("LONORA_SKILL_TEST_IMAGE")
    backend = AnalyticalContainer(real_image) if real_image else fake
    workspace = RunWorkspaceAccess(backend)
    try:
        agent = await fixture.agent("Local analytical packages")
        thread = await fixture.conversation(agent)

        async def fresh() -> ToolContext:
            return replace(
                await fixture.lease(await fixture.run(agent, thread)),
                workspace_access=workspace,
                skill_access=RunSkillAccess(registry, ()),
            )

        context = await fresh()
        results: list[dict[str, Any]] = []
        rounds = 0
        draft = "drafts/statistics"

        async def model(
            _capability: Any, messages: list[ModelMessage], _tools: Any, **_kwargs: Any
        ):
            nonlocal rounds
            rounds += 1
            if rounds > 1:
                result = json.loads(messages[-1].content)
                assert result["ok"], result
                results.append(result)
            if rounds == 1:
                call = ToolCall(
                    id="write-source",
                    name="workspace_update",
                    arguments={
                        "revision": 0,
                        "files": {f"{draft}/SKILL.md": DOCUMENT, f"{draft}/stats.py": SOURCE},
                    },
                )
            elif rounds == 2:
                call = ToolCall(
                    id="create-local",
                    name="skill_package_create",
                    arguments={
                        "source_directory": draft,
                        "workspace_revision": results[-1]["revision"],
                        "version": "1.0.0",
                        "expected_version": 0,
                        "adapted_content": DOCUMENT,
                        "review": REVIEW,
                    },
                )
            elif rounds == 3:
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
                        "workspace_revision": created["workspace_revision"],
                        "utility_path": "skills/local-statistics/1.0.0/stats.py",
                    },
                )
            elif rounds == 4:
                assert results[-1]["exit_code"] == 0 and "mean=2" in results[-1]["stdout"]
                call = ToolCall(
                    id="activate-local",
                    name="skill_package_control",
                    arguments={
                        "skill_id": "local-statistics",
                        "expected_version": results[-1]["resource_version"],
                        "workspace_revision": results[-1]["workspace_revision"],
                        "action": "activate",
                    },
                )
            elif rounds == 5:
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
            assert run.model_metadata["skill_execution_image"] == (real_image or IMAGE)
            row = await session.get(SkillRow, results[1]["resource_id"])
            assert row and row.payload["enabled"]
            entry = row.state["package"]["versions"][0]
            assert entry["workspace_source"]["agent_id"] == agent["id"]
            assert entry["workspace_source"]["run_id"] == context.lease.run_id
            assert entry["workspace_source"]["workspace_revision"] == 1
            current_version = row.version
        print(
            "PASS Agent writes source -> creates disabled local package -> exact utility -> activation -> pinned view; no fake Git or generic enable bypass"
        )

        async def owner_catalog() -> dict[str, Any]:
            page = await fixture.request("GET", f"/agents/{agent['id']}/skills/catalog")
            return next(item for item in page["items"] if item["id"] == "local-statistics")

        with patch.object(fixture.settings, "workspace_socket", None):
            unavailable = await owner_catalog()
            assert not unavailable["available"]
            assert unavailable["code"] == "workspace_execution_unconfigured"
        with patch.object(fixture.settings, "workspace_socket", Path("/tmp/catalog-fixture.sock")):
            for current_image, available in (
                (real_image or IMAGE, True),
                ("sha256:" + "f" * 64, False),
            ):
                with patch.object(
                    WorkspaceClient, "profile", AsyncMock(return_value=current_image)
                ):
                    item = await owner_catalog()
                    assert item["available"] is available
                    if not available:
                        assert item["code"] == "skill_package_validation_required"
            with patch.object(
                WorkspaceClient,
                "profile",
                AsyncMock(side_effect=LonoraError("workspace_profile_unavailable", 503)),
            ):
                item = await owner_catalog()
                assert not item["available"] and item["code"] == "workspace_profile_unavailable"
        print(
            "PASS authenticated owner catalog reflects source verification and actual profile availability"
        )

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
        async with context.db.sessions() as session:
            run = await session.get(RunRow, context.lease.run_id)
            assert run and run.model_metadata["skill_execution_image"] == (real_image or IMAGE)
        print(
            "PASS later Run reuses the same exact local version and profile; receipt replay does not recreate or execute"
        )

        if not real_image:
            fake.image = "sha256:" + "b" * 64
            catalog = await call("changed-profile-list", "skills_list", {"limit": 20})
            local = next(item for item in catalog["skills"] if item["id"] == "local-statistics")
            assert not local["available"] and local["code"] == "skill_package_validation_required"
            await denied(
                call("changed-profile-view", "skill_view", {"skill_id": "local-statistics"}),
                "skill_package_validation_required",
            )
            await denied(
                assert_skill_authority(context, registry, active_ids=["local-statistics"]),
                "skill_continuation_unavailable",
            )
            revision = (await workspace.inspect(context.for_call("revision")))["revision"]
            before = fake.calls
            await denied(
                call(
                    "pinned-profile-execute",
                    "workspace_execute",
                    {
                        "revision": revision,
                        "command": "python3 skills/local-statistics/1.0.0/stats.py",
                    },
                ),
                "workspace_profile_changed",
            )
            assert fake.calls == before
            context = await fresh()
            checked = await call(
                "revalidate-profile",
                "skill_package_validate",
                {
                    "skill_id": "local-statistics",
                    "expected_version": current_version,
                    "workspace_revision": revision,
                    "utility_path": "skills/local-statistics/1.0.0/stats.py",
                },
            )
            current_version = checked["resource_version"]
            activated = await call(
                "reactivate-profile",
                "skill_package_control",
                {
                    "skill_id": "local-statistics",
                    "expected_version": current_version,
                    "workspace_revision": checked["workspace_revision"],
                    "action": "activate",
                },
            )
            current_version = activated["resource_version"]
            assert (await call("new-profile-view", "skill_view", {"skill_id": "local-statistics"}))[
                "skills"
            ]
            print(
                "PASS profile change blocks catalog, restored instructions and pinned execution; fresh Run revalidation restores availability"
            )

        revision = (await workspace.inspect(context.for_call("before-crash")))["revision"]
        crash_doc = DOCUMENT.replace("local-statistics", "recovered-statistics")
        staged = await call(
            "crash-source",
            "workspace_update",
            {
                "revision": revision,
                "files": {"recovery/SKILL.md": crash_doc, "recovery/stats.py": SOURCE},
            },
        )
        create = {
            "source_directory": "recovery",
            "workspace_revision": staged["revision"],
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
                raise RuntimeError("scripted crash after materialized source")
            return await original_create(self, *args, **kwargs)

        with patch.object(SkillRepository, "create", crash_once):
            try:
                await call("recover-create", "skill_package_create", create)
            except RuntimeError:
                pass
            else:
                raise AssertionError("creation crash was not injected")
            recovered = await call("recover-create", "skill_package_create", create)
        assert (
            not recovered["enabled"]
            and recovered["workspace_source"]["workspace_revision"] == staged["revision"]
        )
        assert recovered == await call("recover-create", "skill_package_create", create)
        await denied(
            call("recover-create", "skill_package_create", {**create, "version": "2.0.0"}),
            "skill_package_identity_conflict",
        )
        print(
            "PASS crash after file materialization resumes exact prepared source; same effect cannot change semantic version"
        )

        await denied(
            call("old-revision", "skill_package_create", {**create, "version": "2.0.0"}),
            "workspace_revision_conflict",
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
        async with context.db.sessions() as session, session.begin():
            run = await session.get(RunRow, context.lease.run_id)
            assert run
            run.model_metadata = {**run.model_metadata, "authority": "observe_only"}
        await denied(call("observe-create", "skill_package_create", create), "tool_not_allowed")
        async with context.db.sessions() as session, session.begin():
            run = await session.get(RunRow, context.lease.run_id)
            assert run
            run.model_metadata = {
                key: value for key, value in run.model_metadata.items() if key != "authority"
            }
        print("PASS stale source revision, owner/Agent scope and observe-only creation fail closed")

        revision = (await workspace.inspect(context.for_call("before-tamper")))["revision"]
        await call(
            "tamper-source",
            "workspace_update",
            {
                "revision": revision,
                "files": {"skills/local-statistics/1.0.0/stats.py": "print('changed source')\n"},
            },
        )
        await denied(
            call("tampered-view", "skill_view", {"skill_id": "local-statistics"}),
            "skill_package_source_changed",
        )
        catalog = await call("tampered-list", "skills_list", {"limit": 20})
        assert (
            next(item for item in catalog["skills"] if item["id"] == "local-statistics")["code"]
            == "skill_package_source_changed"
        )
        print(
            "PASS changed installed source invalidates admission even when the catalog remains enabled"
        )

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
        print(
            "PASS existing receipts/catalog/workspace reused; financial approvals and journal unchanged; executor="
            + ("actual-restricted-container" if real_image else "scripted-offline")
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
