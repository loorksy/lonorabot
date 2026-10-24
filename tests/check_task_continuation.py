"""Actual Task slices, worker replacement and effect receipts on disposable PG."""

import asyncio
from dataclasses import replace
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.continuation import MAXIMUM_SLICES, schedule_task_continuation, slice_limit
from lonora_agent.executor import execute_run
from lonora_agent.tasks import TaskSuspended
from lonora_agent.tool_loop import persist as original_persist
from lonora_contracts.domain import Contract, utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.runs import Lease
from lonora_contracts.tasks import TaskControl, TaskCreate
from lonora_core.user_error import LonoraError
from lonora_db.runs import claim_next, require_lease
from lonora_db.schema import EffectReceiptRow, RunRow, TicketRow
from lonora_db.tasks import control_task, create_task, get_task, task_state
from lonora_tools.base import Tool
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_tools.registry import ToolRegistry


class Probe(Contract):
    value: int


async def task_context(f: Fixture, title: str) -> tuple[ToolContext, str]:
    agent = await f.agent(title)
    origin = await f.conversation(agent)
    async with f.runtime.db.sessions() as session, session.begin():
        task = await create_task(
            session, f.owner, agent["id"], origin["id"], TaskCreate(title=title)
        )
        run = await session.get(RunRow, task.payload["run_id"])
        assert run
        data = {"id": run.id, "agent_id": run.agent_id, "thread_id": run.thread_id}
    return await f.lease(data), task.id


async def reclaim(f: Fixture, context: ToolContext, *, expired: bool = False) -> ToolContext:
    if expired:
        async with f.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, context.lease.run_id, with_for_update=True)
            assert row
            row.lease_expires_at = utcnow() - timedelta(seconds=1)
    async with f.runtime.db.sessions() as session, session.begin():
        row = await claim_next(session, "continuation-replacement", 120, "work")
        assert row and row.id == context.lease.run_id
        assert row.lease_owner is not None
        lease = Lease(run_id=row.id, owner=row.lease_owner, fence=row.lease_fence)
    async with f.runtime.db.sessions() as session:
        try:
            await require_lease(session, context.lease)
        except LonoraError as error:
            assert error.code == "stale_lease"
        else:
            raise AssertionError("old continuation worker retained its fence")
    return replace(context, lease=lease)


def response(call: ToolCall | None = None) -> tuple[ModelReply, ModelSelection]:
    return ModelReply(
        tool_calls=[call] if call else [], text="" if call else "تم الفحص والتحقق من النتيجة."
    ), ModelSelection(provider="openai", model="scripted-continuation")


async def main() -> None:
    f = await Fixture().open()
    try:
        ctx, task_id = await task_context(f, "Continue exact pending work")
        effect_count, model_count, crash_once = 0, 0, True

        async def effect(context: ToolContext, arguments: dict[str, Any]) -> dict[str, Any]:
            nonlocal effect_count
            # The handler owns one durable effect receipt. The generic compute
            # continuation cannot mint another effect identity after a crash.
            key = "continuation-probe:" + context.resource_id
            async with context.db.sessions() as session, session.begin():
                prior = await session.get(EffectReceiptRow, key)
                if prior:
                    return prior.result
                result = {"value": arguments["value"], "independently_observed": True}
                session.add(EffectReceiptRow(key=key, result=result))
            effect_count += 1
            return result

        registry = ToolRegistry(
            [t for n, t in load_tools().tools.items() if n != "tool_environment"]
            + [
                Tool(
                    "continuation_probe",
                    "Perform one receipt-backed test effect",
                    Probe,
                    effect,
                    replay_safe=True,
                )
            ]
        )

        async def model(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
            nonlocal model_count
            model_count += 1
            if model_count == 1:
                return response(
                    ToolCall(
                        id="discover-probe",
                        name="tool_environment",
                        arguments={"tool_name": "continuation_probe"},
                    )
                )
            if model_count == 2:
                assert "continuation_probe" in {tool.name for tool in tools}
                return response(
                    ToolCall(id="stable-effect", name="continuation_probe", arguments={"value": 7})
                )
            assert model_count == 3 and effect_count == 1
            assert any(
                message.role == "tool" and message.tool_call_id == "stable-effect"
                for message in messages
            )
            return response()

        async def crash(
            context: ToolContext,
            state: dict[str, Any],
            messages: list[ModelMessage],
            pending: list[ToolCall],
        ) -> None:
            nonlocal crash_once
            if crash_once and effect_count and not pending:
                crash_once = False
                raise asyncio.CancelledError()
            await original_persist(context, state, messages, pending)

        with patch.object(ctx.router, "complete", model):
            await execute_run(ctx, registry, 120, 1)
            async with f.runtime.db.sessions() as session:
                row = await session.get(RunRow, ctx.lease.run_id)
                assert row and row.status == "queued" and effect_count == 0
                assert row.execution_state["rounds"] == 1
                assert row.execution_state["pending"][0]["id"] == "discover-probe"
                assert row.execution_state["task_continuation"]["slice"] == 2
                assert (
                    row.execution_state["environment"]["retry"]["reason_code"]
                    == "task_continuation"
                )
            ctx = await reclaim(f, ctx)
            await execute_run(ctx, registry, 120, 1)
            async with f.runtime.db.sessions() as session:
                row = await session.get(RunRow, ctx.lease.run_id)
                assert row and row.status == "queued" and effect_count == 0
                assert row.execution_state["pending"][0]["id"] == "stable-effect"
                assert row.execution_state["task_continuation"]["slice"] == 3
            ctx = await reclaim(f, ctx)
            with patch("lonora_agent.tool_loop.persist", crash):
                try:
                    await execute_run(ctx, registry, 120, 1)
                except asyncio.CancelledError:
                    pass
                else:
                    raise AssertionError("scripted worker crash did not occur")
            assert effect_count == 1 and model_count == 2
            ctx = await reclaim(f, ctx, expired=True)
            # A changed process configuration cannot enlarge/reset the pinned
            # per-slice budget; replay still consumes the same pending call.
            await execute_run(ctx, registry, 120, 1000)
        async with f.runtime.db.sessions() as session:
            row = await session.get(RunRow, ctx.lease.run_id)
            task = await get_task(session, f.owner, task_id)
            assert row and row.status == "completed" and effect_count == 1 and model_count == 3
            assert row.execution_state["task_continuation"]["rounds_per_slice"] == 1
            assert row.execution_state["task_continuation"]["slice"] == 3
            assert task_state(task).status == "completed"
        print(
            "PASS same Task/Run continues exact last-round calls across worker replacement; receipt-backed effect survives crash exactly once"
        )

        ctx, _ = await task_context(f, "Finite unfinished work")
        turns = 0

        async def endless(_: Any, messages: Any, tools: Any, **kwargs: Any):
            nonlocal turns
            turns += 1
            return response(
                ToolCall(
                    id="bounded-" + str(turns),
                    name="continuation_probe",
                    arguments={"value": turns},
                )
            )

        with patch.object(ctx.router, "complete", endless):
            for index in range(MAXIMUM_SLICES):
                await execute_run(ctx, registry, 120, 1)
                async with f.runtime.db.sessions() as session:
                    row = await session.get(RunRow, ctx.lease.run_id)
                    assert row
                    if index + 1 < MAXIMUM_SLICES:
                        assert row.status == "queued"
                    else:
                        assert row.status == "failed" and row.error_code == "tool_round_limit"
                        assert row.execution_state["task_continuation"]["slice"] == MAXIMUM_SLICES
                        assert row.execution_state["pending"][0]["id"] == "bounded-4"
                if index + 1 < MAXIMUM_SLICES:
                    ctx = await reclaim(f, ctx)
        assert turns == MAXIMUM_SLICES
        print(
            "PASS total model budget stays finite across slices; unfinished work is never reported complete"
        )

        for action in ("pause", "cancel"):
            ctx, identifier = await task_context(f, "Owner " + action + " at boundary")
            state: dict[str, Any] = {
                "rounds": 1,
                "messages": [],
                "pending": [{"id": "must-not-run"}],
            }
            assert slice_limit(state, 1) == 1
            async with f.runtime.db.sessions() as session, session.begin():
                task = await get_task(session, f.owner, identifier)
                await control_task(
                    session,
                    f.owner,
                    TaskControl(task_id=identifier, action=action, expected_version=task.version),
                    agent_id=ctx.agent_id,
                )
            try:
                await schedule_task_continuation(ctx, state, 1)
            except TaskSuspended:
                pass
            else:
                raise AssertionError("owner control did not stop continuation")
            async with f.runtime.db.sessions() as session:
                row = await session.get(RunRow, ctx.lease.run_id)
                task = await session.get(TicketRow, identifier)
                assert row and task
                assert row.status == ("waiting_takeover" if action == "pause" else "cancelled")
                assert task_state(task).status == ("paused" if action == "pause" else "cancelled")
                assert state["task_continuation"]["slice"] == 1
        print(
            "PASS owner pause/cancel wins at continuation boundary without executing pending work"
        )

        agent = await f.agent("Ordinary bounded conversation")
        ctx = await f.lease(await f.run(agent, await f.conversation(agent)))
        state = {"rounds": 1, "messages": [], "pending": [{"id": "ordinary-bound"}]}
        assert not await schedule_task_continuation(ctx, state, 1)
        renewed = await f.lease(
            {"id": ctx.lease.run_id, "agent_id": ctx.agent_id, "thread_id": ctx.thread_id}
        )
        try:
            await schedule_task_continuation(ctx, state, 1)
        except LonoraError as error:
            assert error.code == "stale_lease"
        else:
            raise AssertionError("stale continuation worker accepted")
        assert renewed.lease.fence > ctx.lease.fence
        print(
            "PASS ordinary conversation never acquires automatic Task slices and stale workers cannot schedule them"
        )
    finally:
        await f.close()


asyncio.run(main())
