"""Scripted normal AgentRuntime acceptance on isolated PostgreSQL, no external effects."""

import asyncio
import json
from dataclasses import replace
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.domain import Contract, MessageCreate, utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_contracts.runs import Lease
from lonora_core.user_error import LonoraError
from lonora_db.messages import send_message
from lonora_db.runs import claim_next, require_lease
from lonora_db.schema import AgentRow, RunRow
from lonora_tools.base import Tool
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from lonora_tools.registry import ToolRegistry
from pydantic import Field


class Input(Contract):
    limit: int = Field(default=1, ge=1, le=10)


def reply(call: ToolCall | None = None) -> tuple[ModelReply, ModelSelection]:
    return ModelReply(
        tool_calls=[call] if call else [], text="" if call else "Verified result"
    ), ModelSelection(provider="openai", model="scripted-environment")


def registry_with(tools: list[Tool]) -> ToolRegistry:
    return ToolRegistry(
        [tool for name, tool in load_tools().tools.items() if name != "tool_environment"] + tools
    )


async def context(f: Fixture) -> ToolContext:
    agent = await f.agent("Environment acceptance")
    thread = await f.conversation(agent)
    return await f.lease(await f.run(agent, thread))


async def resumed(f: Fixture, previous: ToolContext) -> ToolContext:
    # Advance only this test Run's durable deadline, never sleep or change production time.
    async with f.runtime.db.sessions() as session, session.begin():
        row = await session.get(RunRow, previous.lease.run_id, with_for_update=True)
        assert row and row.status == "queued"
        state = dict(row.execution_state)
        state["environment"] = {
            **state["environment"],
            "retry": {
                **state["environment"]["retry"],
                "not_before": (utcnow() - timedelta(seconds=1)).isoformat(),
            },
        }
        row.execution_state = state

    async def claim(worker: str) -> Lease | None:
        async with f.runtime.db.sessions() as session, session.begin():
            row = await claim_next(session, worker, 120)
            return Lease(run_id=row.id, owner=worker, fence=row.lease_fence) if row else None

    claims = [item for item in await asyncio.gather(claim("worker-a"), claim("worker-b")) if item]
    assert len(claims) == 1 and claims[0].run_id == previous.lease.run_id
    async with f.runtime.db.sessions() as session:
        try:
            await require_lease(session, previous.lease)
        except LonoraError as error:
            assert error.code == "stale_lease"
        else:
            raise AssertionError("obsolete fence accepted")
    return replace(previous, lease=claims[0])


async def main() -> None:
    f = await Fixture().open()
    try:
        ctx = await context(f)
        attempts, model_turns = 0, 0

        async def flaky(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
            nonlocal attempts
            attempts += 1
            if attempts < 3:
                raise LonoraError(
                    "broker_connection_timeout", 503, diagnostic_message="credential-must-not-leak"
                )
            return {"symbol": "EURUSDm", "candles": [{"close": 1.2}], "limit": args["limit"]}

        async def model(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
            nonlocal model_turns
            model_turns += 1
            if model_turns == 1:
                return reply(ToolCall(id="stable-read", name="probe", arguments={"limit": 1}))
            result = json.loads(messages[-1].content)
            assert result["ok"] and result["symbol"] == "EURUSDm"
            return reply()

        registry = registry_with([Tool("probe", "Read exact test evidence", Input, flaky, True)])
        with patch.object(ctx.router, "complete", model):
            await execute_run(ctx, registry, 120, 8)
            async with f.runtime.db.sessions() as session, session.begin():
                row = await session.get(RunRow, ctx.lease.run_id)
                assert (
                    row
                    and row.status == "queued"
                    and row.execution_state["environment"]["retry"]["attempt"] == 1
                ), (row.status if row else None, row.error_code if row else None)
                assert "credential-must-not-leak" not in json.dumps(row.execution_state)
                assert await claim_next(session, "too-early", 120) is None
            ctx = await resumed(f, ctx)
            await execute_run(ctx, registry, 120, 8)
            assert attempts == 2 and model_turns == 1
            ctx = await resumed(f, ctx)
            await execute_run(ctx, registry, 120, 8)
        async with f.runtime.db.sessions() as session:
            row = await session.get(RunRow, ctx.lease.run_id)
            assert row and row.status == "completed" and attempts == 3 and model_turns == 2
            assert len(row.execution_state["environment"]["recent"]) == 3
        print(
            "PASS safe-read backoff survives worker replacement with stable call ID, one claimant and fencing"
        )
        from lonora_agent.context.environment import operational_context

        async with f.runtime.db.sessions() as session:
            learned = await operational_context(session, f.owner, ctx.agent_id, registry)
            assert "broker_connection_timeout" in learned and "tool_observed" in learned
            assert "event_cursor" in learned and "credential-must-not-leak" not in learned
            assert not await operational_context(session, f.owner, "another-agent", registry)
        print(
            "PASS bounded source-attributed operational history is Agent-scoped and contains no submitted secret"
        )

        ctx = await context(f)
        phase, executed = 0, 0

        async def valid(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
            nonlocal executed
            executed += 1
            return {"limit": args["limit"]}

        registry = registry_with([Tool("probe", "Bounded read", Input, valid, True)])

        async def repair(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
            nonlocal phase
            phase += 1
            if phase == 1:
                return reply(ToolCall(id="bad-1", name="probe", arguments={"limit": 99}))
            result = json.loads(messages[-1].content)
            if phase == 2:
                assert (
                    result["code"] == "tool_arguments_invalid"
                    and result["recovery"]["category"] == "invalid_tool_arguments"
                )
                return reply(
                    ToolCall(id="schema", name="tool_environment", arguments={"tool_name": "probe"})
                )
            if phase == 3:
                assert result["tool"]["input_schema"]["properties"]["limit"]["maximum"] == 10
                assert (
                    result["tool"]["side_effect"] == "read_only"
                    and not result["execution_authorized"]
                )
                return reply(ToolCall(id="fixed", name="probe", arguments={"limit": 2}))
            assert result["ok"] and result["limit"] == 2
            return reply()

        with patch.object(ctx.router, "complete", repair):
            await execute_run(ctx, registry, 120, 8)
        assert phase == 4 and executed == 1
        print("PASS actual schema introspection and same-Run argument repair without owner command")

        ctx = await context(f)
        phase, executed = 0, 0

        async def invalid(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
            nonlocal executed
            executed += 1
            raise LonoraError("chart_indicator_not_found", 404)

        registry = registry_with(
            [
                Tool("probe", "Read missing test indicator", Input, invalid, True),
                Tool("alternative", "Other authorized evidence", Input, valid, True),
            ]
        )

        async def escape(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
            nonlocal phase
            phase += 1
            if phase <= 4:
                return reply(ToolCall(id=f"same-{phase}", name="probe", arguments={"limit": 1}))
            result = json.loads(messages[-1].content)
            if phase == 5:
                assert (
                    result["code"] == "tool_route_exhausted"
                    and result["recovery"]["next_action"] == "alternate_route"
                )
                return reply(ToolCall(id="alternate", name="alternative", arguments={}))
            assert result["ok"]
            return reply()

        with patch.object(ctx.router, "complete", escape):
            await execute_run(ctx, registry, 120, 8)
        # Three failures plus one successful alternative; fourth identical call did not execute.
        assert executed == 4
        print(
            "PASS repeated equivalent failure is blocked even under a new model call ID; alternative continues"
        )

        ctx = await context(f)
        phase, effects = 0, 0

        async def committed(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
            nonlocal effects
            effects += 1
            return {"status": "confirmed", "operation_id": "test-effect", "body": "x" * 130000}

        registry = registry_with([Tool("effect", "Test-only effect", Input, committed)])

        async def oversized(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
            nonlocal phase
            phase += 1
            if phase == 1:
                return reply(ToolCall(id="committed", name="effect", arguments={}))
            result = json.loads(messages[-1].content)
            assert (
                result["ok"]
                and result["operation_id"] == "test-effect"
                and result["context_notice"] == "tool_result_too_large"
            )
            assert result["status"] == "confirmed"
            return reply()

        with patch.object(ctx.router, "complete", oversized):
            await execute_run(ctx, registry, 120, 5)
        assert effects == 1
        print(
            "PASS oversized committed result keeps success and operation identity without effect replay"
        )

        ctx = await context(f)
        phase, effects = 0, 0

        async def ambiguous(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
            nonlocal effects
            effects += 1
            return {
                "status": "ambiguous",
                "code": "broker_result_ambiguous",
                "operation_id": "uncertain-test",
            }

        registry = registry_with(
            [Tool("effect", "Test-only uncertain effect", Input, ambiguous, financial=True)]
        )

        async def uncertain(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
            nonlocal phase
            phase += 1
            if phase <= 2:
                if phase == 2:
                    assert (
                        json.loads(messages[-1].content)["recovery"]["next_action"]
                        == "reconcile_before_any_resend"
                    )
                return reply(ToolCall(id=f"uncertain-{phase}", name="effect", arguments={}))
            assert json.loads(messages[-1].content)["code"] == "broker_result_ambiguous"
            return reply()

        with patch.object(ctx.router, "complete", uncertain):
            await execute_run(ctx, registry, 120, 5)
        assert effects == 1
        print("PASS ambiguous mutation cannot be replayed through a new model call identity")

        ctx = await context(f)

        async def down(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
            raise LonoraError("broker_connection_timeout", 503)

        registry = registry_with([Tool("probe", "Unavailable read", Input, down, True)])
        phase = 0

        async def steering(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
            nonlocal phase
            phase += 1
            if phase == 1:
                return reply(ToolCall(id="superseded-read", name="probe", arguments={}))
            assert messages[-1].role == "user" and messages[-1].content == "Use the new scope"
            return reply()

        with patch.object(ctx.router, "complete", steering):
            await execute_run(ctx, registry, 120, 5)
            async with f.runtime.db.sessions() as session, session.begin():
                sent = await send_message(
                    session, f.owner, ctx.thread_id, MessageCreate(content="Use the new scope")
                )
                assert sent["run_ids"] == [ctx.lease.run_id]
            # Deadline cleared by authenticated admission, no second Run created.
            async with f.runtime.db.sessions() as session, session.begin():
                row = await claim_next(session, "steering", 120)
                assert row and row.id == ctx.lease.run_id
                ctx = replace(
                    ctx, lease=Lease(run_id=row.id, owner="steering", fence=row.lease_fence)
                )
            await execute_run(ctx, registry, 120, 5)
        assert phase == 2
        print("PASS owner steering wakes and supersedes a delayed safe read in the same Run")

        ctx = await context(f)
        phase, effects = 0, 0

        async def interrupted_effect(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
            nonlocal effects
            effects += 1
            raise asyncio.CancelledError()

        registry = registry_with(
            [Tool("unreceipted", "Test-only external mutation", Input, interrupted_effect)]
        )

        async def after_crash(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
            nonlocal phase
            phase += 1
            if phase == 1:
                return reply(ToolCall(id="interrupted-effect", name="unreceipted", arguments={}))
            result = json.loads(messages[-1].content)
            assert (
                result["code"] == "tool_execution_uncertain"
                and not result["recovery"]["safe_to_retry"]
            )
            return reply()

        with patch.object(ctx.router, "complete", after_crash):
            try:
                await execute_run(ctx, registry, 120, 5)
            except asyncio.CancelledError:
                pass
            else:
                raise AssertionError("fixture worker was not interrupted")
            async with f.runtime.db.sessions() as session, session.begin():
                row = await session.get(RunRow, ctx.lease.run_id, with_for_update=True)
                assert (
                    row
                    and row.execution_state["environment"]["inflight"]["call_id"]
                    == "interrupted-effect"
                )
                row.lease_expires_at = utcnow() - timedelta(seconds=1)
            async with f.runtime.db.sessions() as session, session.begin():
                row = await claim_next(session, "crash-recovery", 120)
                assert row and row.id == ctx.lease.run_id
                ctx = replace(
                    ctx, lease=Lease(run_id=row.id, owner="crash-recovery", fence=row.lease_fence)
                )
            await execute_run(ctx, registry, 120, 5)
        assert effects == 1 and phase == 2
        print("PASS worker death after external send does not replay an unreceipted mutation")

        ctx = await context(f)
        phase, reads = 0, 0

        async def large_read(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
            nonlocal reads
            reads += 1
            return {"rows": ["x" * 13000] * args["limit"]}

        registry = registry_with(
            [Tool("bounded_read", "Read with a bounded limit", Input, large_read, True)]
        )

        async def narrower(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
            nonlocal phase
            phase += 1
            if phase == 1:
                return reply(
                    ToolCall(id="large-read", name="bounded_read", arguments={"limit": 10})
                )
            result = json.loads(messages[-1].content)
            if phase == 2:
                assert (
                    result["result_omitted"]
                    and result["recovery"]["next_action"] == "read_stored_result"
                )
                return reply(
                    ToolCall(
                        id="page-result",
                        name="artifact_read",
                        arguments={
                            "artifact_id": result["result_ref"],
                            "offset": 0,
                            "limit": 24000,
                        },
                    )
                )
            assert (
                result["ok"]
                and len(result["content"]) == 24000
                and result["next_offset"] == 24000
                and result["total_chars"] > 120000
            )
            return reply()

        with patch.object(ctx.router, "complete", narrower):
            await execute_run(ctx, registry, 120, 5)
        assert reads == 1 and phase == 3
        print(
            "PASS oversized read is paged from durable storage in the same runtime without repeating the source read"
        )

        ctx = await context(f)
        account = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": "actual-market-recovery", "enabled": True},
            )
        )["id"]
        await f.request(
            "POST",
            f"/trading/connections/{account}/simulation",
            {
                "snapshot": {
                    "currency": "USD",
                    "balance": "10000",
                    "instruments": [
                        {
                            "symbol": "XAUUSDm",
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.01",
                            "volume_max": "10",
                            "volume_step": "0.01",
                        }
                    ],
                    "quotes": {},
                    "candles": {
                        "XAUUSDm:15m": [
                            {
                                "symbol": "XAUUSDm",
                                "timeframe": "15m",
                                "time": (utcnow() - timedelta(minutes=15)).isoformat(),
                                "open": "100",
                                "high": "102",
                                "low": "99",
                                "close": "101",
                                "volume": "10",
                            }
                        ]
                    },
                }
            },
        )
        async with f.runtime.db.sessions() as session, session.begin():
            agent = await session.get(AgentRow, ctx.agent_id)
            assert agent
            agent.role, agent.trading_account_id, agent.trading_symbol = (
                "specialist",
                account,
                "XAUUSDm",
            )
            run = await session.get(RunRow, ctx.lease.run_id)
            assert run
            run.prompt = "Analyze gold using current broker evidence"
        broker = await ctx.brokers.get(f.owner, account)
        original_candles = broker.candles
        phase, attempts = 0, 0

        async def recovered_candles(symbol: str, timeframe: str, limit: int):
            nonlocal attempts
            attempts += 1
            if attempts == 1:
                raise LonoraError("broker_connection_timeout", 503)
            return await original_candles(symbol, timeframe, limit)

        async def analyze(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
            nonlocal phase
            phase += 1
            if phase == 1:
                return reply(
                    ToolCall(
                        id="actual-candles",
                        name="market_candles",
                        arguments={"timeframe": "15m", "limit": 1},
                    )
                )
            result = json.loads(messages[-1].content)
            assert result["ok"] and result["candles"][0]["symbol"] == "XAUUSDm"
            assert str(result["candles"][0]["close"]) == "101"
            return reply()

        with (
            patch.object(broker, "candles", recovered_candles),
            patch.object(ctx.router, "complete", analyze),
        ):
            await execute_run(ctx, load_tools(), 120, 5)
            ctx = await resumed(f, ctx)
            await execute_run(ctx, load_tools(), 120, 5)
        assert phase == 2 and attempts == 2
        print(
            "PASS analyze-gold request recovers through actual bound market_candles and simulation broker without owner symbol repair"
        )

        ctx = await context(f)
        phase = 0
        executed_calls: list[str] = []

        async def financial_receipt(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
            executed_calls.append(context.call_id)
            # Scripted receipt reconciliation, not a second broker send.
            return {
                "operation_id": "same-financial-operation",
                "status": "ambiguous" if len(executed_calls) == 1 else "confirmed",
                "code": "broker_result_ambiguous"
                if len(executed_calls) == 1
                else "broker_confirmed",
            }

        registry = registry_with(
            [
                Tool(
                    "receipted_financial",
                    "Test-only durable receipt",
                    Input,
                    financial_receipt,
                    financial=True,
                    replay_safe=True,
                )
            ]
        )

        async def reconcile(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
            nonlocal phase
            phase += 1
            if phase <= 2:
                return reply(
                    ToolCall(
                        id="original-financial" if phase == 1 else "new-model-id",
                        name="receipted_financial",
                        arguments={},
                    )
                )
            result = json.loads(messages[-1].content)
            assert (
                result["status"] == "confirmed"
                and result["operation_id"] == "same-financial-operation"
            )
            return reply()

        with patch.object(ctx.router, "complete", reconcile):
            await execute_run(ctx, registry, 120, 5)
        assert executed_calls == ["original-financial", "original-financial"]
        print(
            "PASS financial reconciliation consumes the original receipt identity despite a new model call ID"
        )

        ctx = await context(f)
        legacy_effects, phase = 0, 0

        async def legacy_handler(_: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
            nonlocal legacy_effects
            legacy_effects += 1
            return {"status": "confirmed"}

        legacy_call = ToolCall(id="legacy-call", name="legacy_financial", arguments={})
        async with f.runtime.db.sessions() as session, session.begin():
            run = await session.get(RunRow, ctx.lease.run_id, with_for_update=True)
            assert run
            run.execution_state = {
                "messages": [
                    ModelMessage(role="user", content="Legacy interrupted work").model_dump(
                        mode="json"
                    ),
                    ModelMessage(role="assistant", content="", tool_calls=[legacy_call]).model_dump(
                        mode="json"
                    ),
                ],
                "pending": [legacy_call.model_dump(mode="json")],
                "rounds": 1,
            }
        registry = registry_with(
            [
                Tool(
                    "legacy_financial",
                    "Test-only unknown legacy identity",
                    Input,
                    legacy_handler,
                    financial=True,
                    replay_safe=True,
                )
            ]
        )

        async def inspect_legacy(_: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any):
            nonlocal phase
            phase += 1
            result = json.loads(messages[-1].content)
            assert result["code"] in {"tool_execution_uncertain", "broker_result_ambiguous"}
            if phase == 1:
                return reply(ToolCall(id="renamed-legacy", name="legacy_financial", arguments={}))
            return reply()

        with patch.object(ctx.router, "complete", inspect_legacy):
            await execute_run(ctx, registry, 120, 5)
        assert phase == 2 and legacy_effects == 0
        print(
            "PASS an old checkpoint without proven effect identity is fenced, including model-ID alias attempts"
        )

        # Production tool metadata is conservative and never treats financial work as a safe read.
        actual = load_tools()
        for name in ("trade_execute", "trade_close_positions", "goal_step_execute"):
            assert (
                actual.tools[name].financial
                and not actual.tools[name].environment()["safe_automatic_retry"]
            )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
