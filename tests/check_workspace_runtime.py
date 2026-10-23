"""Real PostgreSQL ownership, revision, replay, recovery and Agent tool checks."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_agent.workspace import WorkspaceResult
from lonora_agent.workspace_access import RunWorkspaceAccess
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.schema import (
    AnalyticalWorkspaceRow,
    RunRow,
    TradeApprovalRow,
    TradingJournalRow,
    WorkspaceOperationRow,
)
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from sqlalchemy import func, select

IMAGE = "sha256:" + "a" * 64


class ScriptedExecutor:
    def __init__(self) -> None:
        self.calls = 0
        self.started = asyncio.Event()
        self.release = asyncio.Event()

    async def profile(self) -> str:
        return IMAGE

    async def execute(
        self,
        command: str,
        files: dict[str, bytes] | None = None,
        *,
        deadline_seconds: float = 30,
        expected_image: str | None = None,
    ) -> WorkspaceResult:
        if expected_image is not None and expected_image != IMAGE:
            raise LonoraError("workspace_profile_changed", 409)
        self.calls += 1
        if command == "failure":
            raise LonoraError("workspace_timeout", 408)
        if command == "wait":
            self.started.set()
            await self.release.wait()
        return WorkspaceResult(
            0, "computed\n", "", {**(files or {}), "result.txt": b"verified scripted output"}, IMAGE
        )


async def denied(awaitable: Any, code: str) -> None:
    try:
        await awaitable
    except LonoraError as error:
        assert error.code == code, (error.code, code)
    else:
        raise AssertionError("Expected refusal: " + code)


async def main() -> None:
    fixture = await Fixture().open()
    registry = load_tools()
    checks = 0
    try:
        agent = await fixture.agent("Durable workspace")
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        db = context.db

        async def call(
            identity: str, name: str, arguments: dict[str, Any], ctx: ToolContext = context
        ) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(id=identity, name=name, arguments=arguments), ctx
            )

        async with db.sessions() as session:
            journal = await session.scalar(select(func.count()).select_from(TradingJournalRow))
            approvals = await session.scalar(select(func.count()).select_from(TradeApprovalRow))
        initial = await call("inspect-empty", "workspace_inspect", {})
        assert initial == {
            "revision": 0,
            "files": [],
            "execution_configured": False,
            "active_operation_id": None,
            "recovery_required": False,
        }
        async with db.sessions() as session:
            assert await session.get(AnalyticalWorkspaceRow, agent["id"]) is None
        checks += 1

        edit: dict[str, Any] = {
            "revision": 0,
            "files": {"analysis.py": "print('current evidence')", "notes.txt": "مرحبا"},
            "delete": [],
        }
        created = await call("create-files", "workspace_update", edit)
        assert created["revision"] == 1 and len(created["files"]) == 2
        text = await call(
            "read-notes",
            "workspace_read",
            {"revision": 1, "path": "notes.txt", "offset": 1, "limit": 2},
        )
        assert text["content"] == "رح" and text["next_offset"] == 3
        assert await call("create-files", "workspace_update", edit) == created
        await denied(
            call("create-files", "workspace_update", {**edit, "files": {"different": "changed"}}),
            "workspace_operation_conflict",
        )
        await denied(call("stale-edit", "workspace_update", edit), "workspace_revision_conflict")
        await denied(
            call("stale-read", "workspace_read", {"revision": 0, "path": "notes.txt"}),
            "workspace_revision_conflict",
        )
        checks += 1

        edits = await asyncio.gather(
            *[
                call(
                    f"parallel-{index}",
                    "workspace_update",
                    {"revision": 1, "files": {f"file{index}.txt": str(index)}},
                )
                for index in range(2)
            ],
            return_exceptions=True,
        )
        assert sum(isinstance(result, dict) for result in edits) == 1
        assert (
            sum(
                isinstance(result, LonoraError) and result.code == "workspace_revision_conflict"
                for result in edits
            )
            == 1
        )
        checks += 1

        other = await fixture.agent("Other workspace")
        other_thread = await fixture.conversation(other)
        other_context = await fixture.lease(await fixture.run(other, other_thread))
        await denied(
            call("foreign-owner", "workspace_inspect", {}, replace(context, owner_id=str(uuid4()))),
            "agent_not_found",
        )
        await denied(
            call("foreign-agent", "workspace_inspect", {}, replace(context, agent_id=other["id"])),
            "workspace_scope_mismatch",
        )
        await denied(
            call(
                "foreign-thread",
                "workspace_inspect",
                {},
                replace(context, thread_id=other_thread["id"]),
            ),
            "workspace_scope_mismatch",
        )
        assert (await call("other-empty", "workspace_inspect", {}, other_context))["files"] == []
        checks += 1

        async with db.sessions() as session, session.begin():
            run = await session.get(RunRow, context.lease.run_id)
            assert run
            run.model_metadata = {**run.model_metadata, "authority": "observe_only"}
        await denied(
            call("readonly-write", "workspace_update", {"revision": 2, "files": {"bad": "no"}}),
            "tool_not_allowed",
        )
        await denied(
            call("readonly-exec", "workspace_execute", {"revision": 2, "command": "anything"}),
            "tool_not_allowed",
        )
        assert (await call("readonly-inspect", "workspace_inspect", {}))["revision"] == 2
        async with db.sessions() as session, session.begin():
            run = await session.get(RunRow, context.lease.run_id)
            assert run
            run.model_metadata = {
                key: value for key, value in run.model_metadata.items() if key != "authority"
            }
        checks += 1

        await denied(
            call("no-backend", "workspace_execute", {"revision": 2, "command": "analysis"}),
            "workspace_execution_unconfigured",
        )
        backend = ScriptedExecutor()
        configured = replace(context, workspace_access=RunWorkspaceAccess(backend))
        assert configured.workspace_access is not None
        assert await configured.workspace_access.profile(configured.for_call("profile")) == IMAGE
        assert context.workspace_access is not None
        await denied(
            context.workspace_access.profile(context.for_call("missing-profile")),
            "workspace_execution_unconfigured",
        )
        async with db.sessions() as session, session.begin():
            run = await session.get(RunRow, context.lease.run_id)
            assert run
            run.model_metadata = {**run.model_metadata, "skill_execution_image": "mutable:latest"}
        await denied(
            call(
                "bad-profile",
                "workspace_execute",
                {"revision": 2, "command": "analysis"},
                configured,
            ),
            "workspace_profile_invalid",
        )
        assert backend.calls == 0
        async with db.sessions() as session, session.begin():
            run = await session.get(RunRow, context.lease.run_id)
            assert run
            run.model_metadata = {**run.model_metadata, "skill_execution_image": IMAGE}
        execution = {"revision": 2, "command": "analysis"}
        outcome = await call("execute", "workspace_execute", execution, configured)
        assert outcome["exit_code"] == 0 and outcome["revision"] == 3
        assert outcome["stdout"] == "computed\n" and backend.calls == 1
        assert await call("execute", "workspace_execute", execution, configured) == outcome
        assert backend.calls == 1
        async with db.sessions() as session, session.begin():
            run = await session.get(RunRow, context.lease.run_id)
            assert run
            run.model_metadata = {
                **run.model_metadata,
                "skill_execution_image": "sha256:" + "b" * 64,
            }
        assert await call("execute", "workspace_execute", execution, configured) == outcome
        await denied(
            call(
                "profile-changed",
                "workspace_execute",
                {"revision": 3, "command": "analysis"},
                configured,
            ),
            "workspace_profile_changed",
        )
        assert backend.calls == 1
        assert (await call("profile-refusal-files", "workspace_inspect", {}))["revision"] == 3
        async with db.sessions() as session, session.begin():
            run = await session.get(RunRow, context.lease.run_id)
            assert run
            run.model_metadata = {**run.model_metadata, "skill_execution_image": IMAGE}
        checks += 1

        await denied(
            call("fail", "workspace_execute", {"revision": 3, "command": "failure"}, configured),
            "workspace_timeout",
        )
        repeated = await call(
            "fail", "workspace_execute", {"revision": 3, "command": "failure"}, configured
        )
        assert repeated["ok"] is False and repeated["code"] == "workspace_timeout"
        assert (
            backend.calls == 2
            and (await call("after-failure", "workspace_inspect", {}))["revision"] == 3
        )
        checks += 1

        work = asyncio.create_task(
            call("waiting", "workspace_execute", {"revision": 3, "command": "wait"}, configured)
        )
        await asyncio.wait_for(backend.started.wait(), 5)
        await denied(
            call("busy-write", "workspace_update", {"revision": 3, "files": {"bad": "no"}}),
            "workspace_busy",
        )
        # No DB transaction/Agent lock is held while the backend runs.
        assert (await call("live-inspect", "workspace_inspect", {}))["active_operation_id"]
        work.cancel()
        try:
            await work
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError("Cancellation lost")
        assert (await call("cancel-inspect", "workspace_inspect", {}))[
            "active_operation_id"
        ] is None
        checks += 1

        # Simulate replacement while the previous worker still has a result in
        # flight. A newly fenced worker can recover the same persistent files.
        backend.started.clear()
        late = asyncio.create_task(
            call("late", "workspace_execute", {"revision": 3, "command": "wait"}, configured)
        )
        await asyncio.wait_for(backend.started.wait(), 5)
        replacement = await fixture.lease(
            {"id": context.lease.run_id, "agent_id": agent["id"], "thread_id": thread["id"]}
        )
        replacement = replace(replacement, workspace_access=RunWorkspaceAccess(backend))
        resumed = await call(
            "late", "workspace_execute", {"revision": 3, "command": "wait"}, replacement
        )
        assert resumed["code"] == "workspace_execution_interrupted"
        assert backend.calls == 4, "Recovery blindly reran an interrupted operation"
        newer = await call(
            "replacement-files",
            "workspace_update",
            {"revision": 3, "files": {"result.txt": "new authoritative result"}},
            replacement,
        )
        assert newer["revision"] == 4
        backend.release.set()
        await denied(late, "stale_lease")
        text = await call(
            "new-result", "workspace_read", {"revision": 4, "path": "result.txt"}, replacement
        )
        assert text["content"] == "new authoritative result"
        checks += 1

        # Fresh service object, same Agent/DB; no in-memory filesystem is needed.
        restarted = replace(replacement, workspace_access=RunWorkspaceAccess())
        assert (await call("restart-inspect", "workspace_inspect", {}, restarted))["revision"] == 4
        assert (
            await call(
                "restart-read", "workspace_read", {"revision": 4, "path": "notes.txt"}, restarted
            )
        )["content"] == "مرحبا"
        checks += 1

        # Canonical Agent loop consumes the same ordinary tool definitions.
        rounds = 0

        async def model(*_args: Any, **_kwargs: Any):
            nonlocal rounds
            rounds += 1
            if rounds == 1:
                reply = ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="model-files",
                            name="workspace_update",
                            arguments={
                                "revision": 0,
                                "files": {"from-agent.txt": "saved by the canonical loop"},
                            },
                        )
                    ]
                )
            elif rounds == 2:
                reply = ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="model-read",
                            name="workspace_read",
                            arguments={"revision": 1, "path": "from-agent.txt"},
                        )
                    ]
                )
            else:
                reply = ModelReply(text="The analysis file is saved.")
            return reply, ModelSelection(provider="openai", model="scripted-workspace")

        with patch.object(other_context.router, "complete", model):
            await execute_run(other_context, registry, 120, 5)
        async with db.sessions() as session:
            run = await session.get(RunRow, other_context.lease.run_id)
            assert run and run.status == "completed"
            stored = await session.get(AnalyticalWorkspaceRow, other["id"])
            assert stored and stored.revision == 1
            assert (
                await session.scalar(select(func.count()).select_from(TradingJournalRow)) == journal
            )
            assert (
                await session.scalar(select(func.count()).select_from(TradeApprovalRow))
                == approvals
            )
        checks += 1

        async with db.sessions() as session, session.begin():
            run = await session.get(RunRow, replacement.lease.run_id)
            assert run
            run.lease_expires_at = utcnow() - timedelta(seconds=1)
        await denied(call("expired-read", "workspace_inspect", {}, replacement), "stale_lease")
        await fixture.request("DELETE", "/agents/" + agent["id"])
        fixture.agents.remove(agent["id"])
        async with db.sessions() as session:
            assert await session.get(AnalyticalWorkspaceRow, agent["id"]) is None
            assert not list(
                await session.scalars(
                    select(WorkspaceOperationRow).where(
                        WorkspaceOperationRow.agent_id == agent["id"]
                    )
                )
            )
        checks += 1
        print(
            f"PASS: {checks} PostgreSQL workspace ownership/revision/replay/recovery/Agent-loop checks; zero financial effects"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
