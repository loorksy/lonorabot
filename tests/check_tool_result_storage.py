"""Real fenced tool-loop/PG recovery with scripted effects; never touches a broker."""

import asyncio
import json
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.context import omitted_result
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.environment import bounded_result, observe
from lonora_agent.tool_loop import execute_tool_loop, persist
from lonora_contracts.domain import Contract
from lonora_contracts.model_routing import ModelSelection
from lonora_core.attachments import MAX_ATTACHMENT_BYTES
from lonora_core.user_error import LonoraError
from lonora_db.artifacts import ArtifactRepository
from lonora_db.generated_artifacts import pending_generated_artifacts
from lonora_db.schema import ArtifactRow, RunRow
from lonora_security.runtime_storage import confined_path
from lonora_tools.artifacts import read
from lonora_tools.base import Tool
from lonora_tools.context import ToolContext
from lonora_tools.registry import ToolRegistry
from lonora_tools.tool_results import result_identity, store_result, stored_result


async def main() -> None:
    fixture = await Fixture().open()
    with TemporaryDirectory() as directory:
        root = Path(directory)
        try:
            agent = await fixture.agent("Stored observations")
            thread = await fixture.conversation(agent)

            async def context() -> ToolContext:
                return replace(
                    await fixture.lease(await fixture.run(agent, thread)), artifact_root=root
                )

            ctx = await context()
            call = ToolCall(id="one-mutation", name="scripted_mutation", arguments={})
            data: dict[str, Any] = {
                "ok": True,
                "status": "confirmed",
                "operation_id": "simulation-only-001",
                "broker_reference": "ticket-123",
                "data": "سوق" * 70000,
                "api_key": "never-save-this",
                "nested": {"authorization": "never-save-this-either"},
            }
            attempts = 0

            async def mutation(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
                nonlocal attempts
                attempts += 1
                return data

            registry = ToolRegistry(
                [Tool(call.name, "Scripted effect", Contract, mutation, financial=True)]
            )
            messages = [
                ModelMessage(role="user", content="Scripted fixture"),
                ModelMessage(role="assistant", content="", tool_calls=[call]),
            ]
            await persist(ctx, {"environment": {"version": 1}}, messages, [call])

            async def interrupted_persist(
                c: ToolContext,
                state: dict[str, Any],
                rows: list[ModelMessage],
                pending: list[ToolCall],
            ) -> None:
                if rows[-1].role == "tool":
                    raise RuntimeError("simulated death after receipt before checkpoint")
                await persist(c, state, rows, pending)

            with patch("lonora_agent.tool_loop.persist", interrupted_persist):
                try:
                    await execute_tool_loop(ctx, registry, 8)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("expected injected death")
            assert attempts == 1
            async with ctx.db.sessions() as session:
                run = await session.get(RunRow, ctx.lease.run_id)
                assert run and run.execution_state["environment"]["inflight"]["call_id"] == call.id
                artifact = await session.get(ArtifactRow, result_identity(ctx, call))
                assert artifact
                path = confined_path(root, artifact.payload["key"])
                assert "never-save-this" not in path.read_text()
                assert not await pending_generated_artifacts(session, ctx.owner_id, run)
                assert not await ArtifactRepository().list(session, ctx.owner_id)

            async def model(*args: Any, **kwargs: Any) -> tuple[ModelReply, ModelSelection]:
                rows: list[ModelMessage] = args[1]
                result = json.loads(rows[-1].content)
                assert result["ok"] and result["status"] == "confirmed"
                assert result["operation_id"] == "simulation-only-001"
                assert result["result_ref"] == result_identity(ctx, call)
                return ModelReply(text="verified"), ModelSelection(
                    provider="openai", model="scripted"
                )

            with patch("lonora_agent.tool_loop.model_turn", model):
                outcome = await execute_tool_loop(ctx, registry, 8)
            assert outcome.text == "verified" and attempts == 1
            pointer = await stored_result(ctx, call)
            assert pointer and pointer["result_format"] == "redacted_json"
            assert (
                json.loads(omitted_result(json.dumps(pointer), 4096))["result_ref"]
                == pointer["result_ref"]
            )
            pieces: list[str] = []
            offset = 0
            while True:
                page = await read(
                    ctx, {"artifact_id": pointer["result_ref"], "offset": offset, "limit": 24000}
                )
                assert len(page["content"]) <= 24000
                pieces.append(page["content"])
                if page["next_offset"] is None:
                    break
                offset = page["next_offset"]
            recovered = json.loads("".join(pieces))
            assert recovered["data"] == data["data"] and recovered["api_key"] == "[redacted]"
            other = await fixture.agent("Other scope")
            other_thread = await fixture.conversation(other)
            for wrong in (
                replace(ctx, agent_id=other["id"]),
                replace(ctx, thread_id=other_thread["id"]),
                replace(ctx, owner_id="not-owner"),
            ):
                try:
                    await read(wrong, {"artifact_id": pointer["result_ref"]})
                except LonoraError as error:
                    assert error.code == "artifacts_not_found"
                else:
                    raise AssertionError("cross-scope receipt read")
            try:
                await stored_result(ctx, call.model_copy(update={"arguments": {"different": True}}))
            except LonoraError as error:
                assert error.code == "tool_result_identity_conflict"
            else:
                raise AssertionError("reused call identity accepted")
            path.write_text("corrupt")
            missing = await stored_result(ctx, call)
            assert (
                missing
                and missing["ok"]
                and missing["result_storage_error"] == "tool_result_file_unavailable"
            )
            try:
                await read(ctx, {"artifact_id": pointer["result_ref"]})
            except LonoraError as error:
                assert error.code == "artifact_integrity_failed"
            else:
                raise AssertionError("corrupt bytes accepted")
            path.unlink()
            assert (await stored_result(ctx, call) or {})["operation_id"] == "simulation-only-001"
            print(
                "PASS actual ToolLoop crash recovery consumes receipt without repeating mutation; scoped paging, redaction, corruption/missing data"
            )

            ambiguous_ctx = await context()
            journal: dict[str, Any] = {}
            reconciliation_reads = 0

            async def journaled(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
                nonlocal reconciliation_reads
                if journal:
                    reconciliation_reads += 1
                    return {"ok": True, "status": "confirmed", "operation_id": journal["id"]}
                journal["id"] = "same-operation"
                return {
                    "ok": True,
                    "status": "ambiguous",
                    "operation_id": journal["id"],
                    "data": "x" * 130000,
                }

            ambiguous_registry = ToolRegistry(
                [
                    Tool(
                        call.name,
                        "Scripted journal reconciliation",
                        Contract,
                        journaled,
                        financial=True,
                        replay_safe=True,
                    )
                ]
            )
            await persist(ambiguous_ctx, {"environment": {"version": 1}}, messages, [call])
            with patch("lonora_agent.tool_loop.persist", interrupted_persist):
                try:
                    await execute_tool_loop(ambiguous_ctx, ambiguous_registry, 8)
                except RuntimeError:
                    pass
                else:
                    raise AssertionError("missing injected death")

            async def reconciled(*args: Any, **kwargs: Any) -> tuple[ModelReply, ModelSelection]:
                observed = json.loads(args[1][-1].content)
                assert (
                    observed["status"] == "confirmed"
                    and observed["operation_id"] == "same-operation"
                )
                return ModelReply(text="reconciled"), ModelSelection(
                    provider="openai", model="scripted"
                )

            with patch("lonora_agent.tool_loop.model_turn", reconciled):
                await execute_tool_loop(ambiguous_ctx, ambiguous_registry, 8)
            assert reconciliation_reads == 1 and journal == {"id": "same-operation"}
            print(
                "PASS large ambiguous financial observation allows same-operation journal reconciliation, never a new effect"
            )

            failed_ctx = await context()
            await persist(failed_ctx, {"environment": {"version": 1}}, messages, [call])
            captured: list[dict[str, Any]] = []

            async def failed_storage_model(
                *args: Any, **kwargs: Any
            ) -> tuple[ModelReply, ModelSelection]:
                captured.append(json.loads(args[1][-1].content))
                return ModelReply(text="verified"), ModelSelection(
                    provider="openai", model="scripted"
                )

            with (
                patch(
                    "lonora_tools.artifacts.write_artifact_file",
                    side_effect=PermissionError("no write"),
                ),
                patch("lonora_agent.tool_loop.model_turn", failed_storage_model),
            ):
                await execute_tool_loop(failed_ctx, registry, 8)
            assert (
                attempts == 2
                and captured[0]["ok"]
                and captured[0]["operation_id"] == "simulation-only-001"
            )
            assert captured[0]["result_persisted"] is False
            assert captured[0]["result_storage_error"] == "tool_result_storage_unavailable"
            async with failed_ctx.db.sessions() as session:
                assert await session.get(ArtifactRow, result_identity(failed_ctx, call)) is None
            print(
                "PASS file write failure preserves successful effect and checkpoints without retry"
            )

            stale = replace(ctx, lease=ctx.lease.model_copy(update={"fence": ctx.lease.fence - 1}))
            try:
                await store_result(stale, call, data, bounded_result(data))
            except LonoraError as error:
                assert error.code == "stale_lease"
            else:
                raise AssertionError("stale fence wrote receipt")
            batch = {
                "ok": True,
                "results": [{"status": "confirmed"}] * 25 + [{"status": "ambiguous"}],
            }
            observe({}, call, registry.tools[call.name], batch)
            summary = bounded_result(batch)
            assert summary["status"] == "ambiguous"
            state: dict[str, Any] = {}
            assert observe(state, call, registry.tools[call.name], summary)["ambiguous"]
            too_big = {"ok": True, "data": "x" * MAX_ATTACHMENT_BYTES}
            try:
                await store_result(
                    ctx, call.model_copy(update={"id": "too-big"}), too_big, bounded_result(too_big)
                )
            except LonoraError as error:
                assert error.code == "attachment_too_large"
            else:
                raise AssertionError("unbounded stored result")
            # More than the normal list limit of internal rows must not crowd
            # ordinary artifacts out before the SQL predicate is applied.
            async with ctx.db.sessions() as session, session.begin():
                visible = await ArtifactRepository().create(
                    session,
                    ctx.owner_id,
                    {"name": "visible"},
                    agent_id=ctx.agent_id,
                    thread_id=ctx.thread_id,
                )
                visible_id = visible.id
                session.add_all(
                    [
                        ArtifactRow(
                            owner_id=ctx.owner_id,
                            agent_id=ctx.agent_id,
                            thread_id=ctx.thread_id,
                            payload={},
                            state={
                                "internal_tool_result": True,
                                "producer_run_id": ctx.lease.run_id,
                            },
                        )
                        for _ in range(205)
                    ]
                )
            async with ctx.db.sessions() as session:
                assert [
                    row.id for row in await ArtifactRepository().list(session, ctx.owner_id)
                ] == [visible_id]
                run = await session.get(RunRow, ctx.lease.run_id)
                assert run and not await pending_generated_artifacts(session, ctx.owner_id, run)
            print(
                "PASS stale fence, 20MB bound, ambiguity beyond summary, internal SQL filtering before list limit"
            )
        finally:
            await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
