"""Real PostgreSQL/ToolLoop package lifecycle, with optional real Docker validation."""

import asyncio
import json
import os
from dataclasses import replace
from io import BytesIO
from typing import Any
from unittest.mock import patch
from uuid import uuid4
from zipfile import ZipFile

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_agent.skills.access import RunSkillAccess
from lonora_agent.workspace import AnalyticalContainer, WorkspaceResult
from lonora_agent.workspace_access import RunWorkspaceAccess
from lonora_contracts.model_routing import ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.schema import RunRow, SkillRow, TradeApprovalRow, TradingJournalRow
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from sqlalchemy import func, select

DOCUMENT = "---\nname: sample\ndescription: Compute statistics from verified historical observations.\n---\nUse exact owner-provided observations. These procedures never authorize financial actions.\n"
REVIEW = {
    "source_behavior": "Compute a mean from a known, bounded historical input sample.",
    "adapted_behavior": "Compute a mean using owner-supplied data under the existing isolated workspace.",
    "assumptions": [
        "Historical values here are a test fixture, not a current market recommendation."
    ],
    "limitations": [
        "This smoke test does not validate a trading strategy, instrument equivalence or predictive quality."
    ],
}
COMMIT = "c" * 40
IMAGE = "sha256:" + "a" * 64
SOURCE = "import json\nfrom pathlib import Path\nvalues = [1, 2, 3]\nassert len(values) == 3\nPath('mean.json').write_text(json.dumps({'mean': sum(values)/len(values)}))\nprint('mean=2.0')\n"


def archive(source: str = SOURCE) -> bytes:
    output = BytesIO()
    with ZipFile(output, "w") as bundle:
        bundle.writestr("root/sample/SKILL.md", DOCUMENT)
        bundle.writestr("root/sample/analyze.py", source)
    return output.getvalue()


class ScriptedExecutor:
    def __init__(self) -> None:
        self.calls = 0

    async def execute(
        self, command: str, files: dict[str, bytes] | None = None, *, deadline_seconds: float = 30
    ) -> WorkspaceResult:
        self.calls += 1
        assert command.startswith("python3 skills/sample/") and deadline_seconds == 30
        snapshot = dict(files or {})
        utility = next(name for name in snapshot if name.endswith("/analyze.py"))
        if b"lonora_dependency_that_is_not_available" in snapshot[utility]:
            return WorkspaceResult(
                1,
                "",
                "ModuleNotFoundError: lonora_dependency_that_is_not_available",
                snapshot,
                IMAGE,
            )
        if b"Path(__file__).write_text" in snapshot[utility]:
            snapshot[utility] = b"print('changed source')\n"
            return WorkspaceResult(0, "source changed\n", "", snapshot, IMAGE)
        return WorkspaceResult(0, "mean=2.0\n", "", dict(files or {}), IMAGE)


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
    executor = ScriptedExecutor()
    image = os.environ.get("LONORA_SKILL_TEST_IMAGE")
    workspace = RunWorkspaceAccess(AnalyticalContainer(image) if image else executor)
    checks = 0
    fetched = 0

    async def fetch(_url: str, commit: str) -> bytes:
        nonlocal fetched
        fetched += 1
        return archive(SOURCE if commit == COMMIT else SOURCE + "# Version two\n")

    try:
        agent = await fixture.agent("Package lifecycle")
        thread = await fixture.conversation(agent)
        context = replace(
            await fixture.lease(await fixture.run(agent, thread)),
            workspace_access=workspace,
            skill_access=RunSkillAccess(registry, ()),
        )
        db = context.db
        request = {
            "repository_url": "https://github.com/example/research",
            "commit": COMMIT,
            "source_path": "sample/SKILL.md",
            "version": "1.0.0",
            "adapted_content": DOCUMENT,
            "review": REVIEW,
            "expected_version": 0,
            "workspace_revision": 0,
        }
        results: list[dict[str, Any]] = []
        rounds = 0

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
                call = ToolCall(id="import", name="skill_package_import", arguments=request)
            elif rounds == 2:
                call = ToolCall(
                    id="validate",
                    name="skill_package_validate",
                    arguments={
                        "skill_id": "sample",
                        "expected_version": results[-1]["resource_version"],
                        "workspace_revision": results[-1]["workspace_revision"],
                        "utility_path": "skills/sample/1.0.0/analyze.py",
                    },
                )
            elif rounds == 3:
                assert results[-1]["exit_code"] == 0 and "mean=2.0" in results[-1]["stdout"]
                call = ToolCall(
                    id="activate",
                    name="skill_package_control",
                    arguments={
                        "skill_id": "sample",
                        "expected_version": results[-1]["resource_version"],
                        "workspace_revision": results[-1]["workspace_revision"],
                        "action": "activate",
                    },
                )
            elif rounds == 4:
                call = ToolCall(id="view", name="skill_view", arguments={"skill_id": "sample"})
            else:
                assert "exact owner-provided" in results[-1]["skills"][0]["content"]
                return ModelReply(
                    text="The isolated historical calculation completed; its reusable procedure is available."
                ), ModelSelection(provider="openai", model="scripted-package")
            return ModelReply(tool_calls=[call]), ModelSelection(
                provider="openai", model="scripted-package"
            )

        async with db.sessions() as session:
            journal = await session.scalar(select(func.count()).select_from(TradingJournalRow))
            approvals = await session.scalar(select(func.count()).select_from(TradeApprovalRow))
        with (
            patch("lonora_agent.skills.lifecycle.fetch_package", fetch),
            patch.object(context.router, "complete", model),
        ):
            await execute_run(context, registry, 120, 8)
        async with db.sessions() as session:
            run = await session.get(RunRow, context.lease.run_id)
            assert run and run.status == "completed", run.error_code if run else None
            assert "sample" in run.model_metadata["skill_snapshot"]["skills"]
            row = await session.get(SkillRow, results[0]["resource_id"])
            assert row and row.payload["enabled"] and len(row.state["package"]["versions"]) == 1
            assert (
                not results[0]["semantic_equivalence_verified"]
                and not results[0]["authority_granted"]
            )
            version = row.version
        assert fetched == 1
        checks += 1
        context = replace(
            await fixture.lease(await fixture.run(agent, thread)),
            workspace_access=workspace,
            skill_access=RunSkillAccess(registry, ()),
        )

        async def call(
            identity: str, name: str, arguments: dict[str, Any], ctx: ToolContext = context
        ) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(id=identity, name=name, arguments=arguments), ctx
            )

        with patch("lonora_agent.skills.lifecycle.fetch_package", fetch):
            revision = (await workspace.inspect(context.for_call("inspect")))["revision"]
            update = {
                **request,
                "version": "2.0.0",
                "commit": "d" * 40,
                "adapted_content": DOCUMENT + "\nSecond version: preserve source timestamps.",
                "expected_version": version,
                "workspace_revision": revision,
            }
            second = await call("update", "skill_package_import", update)
            assert second["version"] == "2.0.0" and not second["enabled"]
            assert await call("update", "skill_package_import", update) == second
            assert fetched == 2
            await denied(
                call(
                    "update",
                    "skill_package_import",
                    {**update, "adapted_content": DOCUMENT + "changed"},
                ),
                "skill_package_identity_conflict",
            )
            await denied(
                call(
                    "too-soon",
                    "skill_package_control",
                    {
                        "skill_id": "sample",
                        "expected_version": second["resource_version"],
                        "workspace_revision": second["workspace_revision"],
                        "action": "activate",
                    },
                ),
                "skill_package_validation_required",
            )
            checks += 1
            rolled = await call(
                "rollback",
                "skill_package_control",
                {
                    "skill_id": "sample",
                    "expected_version": second["resource_version"],
                    "workspace_revision": second["workspace_revision"],
                    "action": "rollback",
                    "target_version": "1.0.0",
                },
            )
            assert rolled["version"] == "1.0.0" and not rolled["enabled"]
            assert (
                await call(
                    "rollback",
                    "skill_package_control",
                    {
                        "skill_id": "sample",
                        "expected_version": second["resource_version"],
                        "workspace_revision": second["workspace_revision"],
                        "action": "rollback",
                        "target_version": "1.0.0",
                    },
                )
                == rolled
            )
            enabled = await call(
                "reactivate",
                "skill_package_control",
                {
                    "skill_id": "sample",
                    "expected_version": rolled["resource_version"],
                    "workspace_revision": second["workspace_revision"],
                    "action": "activate",
                },
            )
            assert enabled["enabled"]
            checks += 1
            await denied(
                call(
                    "foreign",
                    "skill_package_control",
                    {
                        "skill_id": "sample",
                        "expected_version": enabled["resource_version"],
                        "workspace_revision": second["workspace_revision"],
                        "action": "disable",
                    },
                    replace(context, owner_id=str(uuid4())),
                ),
                "agent_not_found",
            )
            async with db.sessions() as session, session.begin():
                run = await session.get(RunRow, context.lease.run_id)
                assert run
                run.model_metadata = {**run.model_metadata, "authority": "observe_only"}
            await denied(call("observe", "skill_package_import", update), "tool_not_allowed")
            async with db.sessions() as session, session.begin():
                run = await session.get(RunRow, context.lease.run_id)
                assert run
                run.model_metadata = {
                    key: value for key, value in run.model_metadata.items() if key != "authority"
                }
            checks += 1
            controls = await fixture.request(
                "POST",
                f"/agents/{agent['id']}/skills/revocations",
                {
                    "skill_id": "sample",
                    "version": "1.0.0",
                    "expected_revision": 0,
                    "reason": "unsafe",
                },
            )
            assert controls["revision"] == 1
            await denied(
                call(
                    "revoked-activate",
                    "skill_package_control",
                    {
                        "skill_id": "sample",
                        "expected_version": enabled["resource_version"],
                        "workspace_revision": second["workspace_revision"],
                        "action": "activate",
                    },
                ),
                "skill_version_revoked",
            )
            await denied(
                call(
                    "relabel",
                    "skill_package_import",
                    {
                        **request,
                        "version": "3.0.0",
                        "workspace_revision": second["workspace_revision"],
                        "expected_version": enabled["resource_version"],
                    },
                ),
                "skill_version_revoked",
            )
            removed = await call(
                "remove",
                "skill_package_control",
                {
                    "skill_id": "sample",
                    "expected_version": enabled["resource_version"],
                    "workspace_revision": second["workspace_revision"],
                    "action": "remove",
                },
            )
            assert removed["status"] == "removed"
            assert (
                await call(
                    "remove",
                    "skill_package_control",
                    {
                        "skill_id": "sample",
                        "expected_version": enabled["resource_version"],
                        "workspace_revision": second["workspace_revision"],
                        "action": "remove",
                    },
                )
                == removed
            )
            await denied(
                call(
                    "reinstall-denied",
                    "skill_package_import",
                    {
                        **request,
                        "version": "4.0.0",
                        "workspace_revision": second["workspace_revision"],
                    },
                ),
                "skill_version_revoked",
            )
            checks += 1
            stale = context
            replacement = await fixture.lease(
                {
                    "id": context.lease.run_id,
                    "agent_id": context.agent_id,
                    "thread_id": context.thread_id,
                }
            )
            await denied(call("stale", "skill_package_import", request, stale), "stale_lease")
            assert replacement.lease.fence > stale.lease.fence
            checks += 1
        # A real process failure is useful evidence, never successful validation.
        # Changed source bytes must also invalidate an otherwise zero exit status.
        for index, source in enumerate(
            (
                "import lonora_dependency_that_is_not_available\n",
                "from pathlib import Path\nPath(__file__).write_text(\"print('changed source')\\n\")\n",
            )
        ):
            failed_agent = await fixture.agent("Untrusted package validation")
            failed_context = replace(
                await fixture.lease(
                    await fixture.run(failed_agent, await fixture.conversation(failed_agent))
                ),
                workspace_access=workspace,
                skill_access=RunSkillAccess(registry, ()),
            )
            with patch("lonora_agent.skills.lifecycle.fetch_package", return_value=archive(source)):
                imported = await registry.execute(
                    ToolCall(id="import-failed", name="skill_package_import", arguments=request),
                    failed_context,
                )
            validation = ToolCall(
                id="validate-failed",
                name="skill_package_validate",
                arguments={
                    "skill_id": "sample",
                    "expected_version": imported["resource_version"],
                    "workspace_revision": imported["workspace_revision"],
                    "utility_path": "skills/sample/1.0.0/analyze.py",
                },
            )
            if index == 0:
                outcome = await registry.execute(validation, failed_context)
                assert outcome["exit_code"] != 0 and outcome["status"] == "smoke_test_failed"
                assert "lonora_dependency_that_is_not_available" in outcome["stderr"]
                assert await registry.execute(validation, failed_context) == outcome
                await denied(
                    registry.execute(
                        ToolCall(
                            id="activate-failed",
                            name="skill_package_control",
                            arguments={
                                "skill_id": "sample",
                                "expected_version": outcome["resource_version"],
                                "workspace_revision": outcome["workspace_revision"],
                                "action": "activate",
                            },
                        ),
                        failed_context,
                    ),
                    "skill_package_validation_required",
                )
            else:
                await denied(
                    registry.execute(validation, failed_context), "skill_package_source_changed"
                )
            async with db.sessions() as session:
                row = await session.get(SkillRow, imported["resource_id"])
                assert row is not None and not row.payload["enabled"]
                if index == 1:
                    assert row.state["package"]["versions"][0]["validation"] is None
            checks += 1
        async with db.sessions() as session:
            assert (
                await session.scalar(select(func.count()).select_from(TradingJournalRow)) == journal
            )
            assert (
                await session.scalar(select(func.count()).select_from(TradeApprovalRow))
                == approvals
            )
        print(
            f"PASS {checks} package lifecycle groups: canonical Agent import/isolated validation/activation/view, immutable updates, replay, rollback, ownership, observe-only, revocation/relabel/removal, stale lease, missing dependency and self-modifying source; financial state unchanged; executor={'real-networkless-container' if image else 'scripted-offline'}"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
