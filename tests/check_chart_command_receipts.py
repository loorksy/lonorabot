"""Disposable PostgreSQL native chart-command and real ToolLoop crash recovery checks."""

import asyncio
import json
from dataclasses import replace
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.tool_loop import execute_tool_loop, persist
from lonora_charts.state import ChartCommand
from lonora_contracts.chart import ChartState
from lonora_contracts.model_routing import ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.cloud_charts import CloudChartRepository
from lonora_db.schema import EffectReceiptRow, TradingJournalRow
from lonora_tools import chart_state
from lonora_tools.registry import ToolRegistry
from sqlalchemy import func, select


class WorkerKilled(BaseException):
    pass


async def main() -> None:
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Receipt verification")
        thread = await fixture.conversation(agent)
        run = await fixture.run(agent, thread)
        context = await fixture.lease(run)
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": "receipt-" + uuid4().hex,
                "enabled": True,
            },
        )
        async with context.db.sessions() as session, session.begin():
            row = await CloudChartRepository().create(
                session,
                context.owner_id,
                ChartState(
                    account_id=connection["id"],
                    symbol="XAUUSDm",
                    timeframe="1h",
                    annotations=[{"id": "manual", "type": "price", "price": 100}],
                ).model_dump(mode="json"),
                agent_id=agent["id"],
                thread_id=thread["id"],
            )
            chart_id = row.id
        registry = ToolRegistry(chart_state.tools())
        version = 1
        for index, (name, extra) in enumerate(
            [
                ("chart_set_symbol", {"symbol": "EURUSDm"}),
                ("chart_set_timeframe", {"timeframe": "15m"}),
                ("chart_add_indicator", {"name": "sma", "period": 14}),
                ("chart_remove_indicator", {"name": "sma", "period": 14}),
                ("chart_annotate", {"annotation": {"type": "price", "price": 101}}),
            ]
        ):
            call = ToolCall(
                id=f"command-{index}",
                name=name,
                arguments={"chart_id": chart_id, "version": version, **extra},
            )
            result = await registry.execute(call, context)
            assert result["command"]["revision"] == version + 1
            assert result["requires_scene_inspection"] and result["scene"] is None
            assert result == await registry.execute(call, context)
            changed = call.model_copy(update={"arguments": {**call.arguments, "version": 999}})
            try:
                await registry.execute(changed, context)
            except LonoraError as error:
                assert error.code == "chart_command_identity_conflict"
            else:
                raise AssertionError("Same call different arguments accepted")
            version += 1
        # Failed atomic drawing batch does not acquire a receipt or commit any prefix.
        bad = ToolCall(
            id="invalid-batch",
            name="chart_annotate",
            arguments={
                "chart_id": chart_id,
                "version": version,
                "operations": [
                    {"op": "add", "annotation": {"type": "price", "price": 105}},
                    {"op": "delete", "id": "missing"},
                ],
            },
        )
        try:
            await registry.execute(bad, context)
        except LonoraError as error:
            assert error.code == "chart_annotation_not_found"
        else:
            raise AssertionError("Invalid batch accepted")
        command = ChartCommand(
            context.owner_id,
            context.agent_id,
            context.thread_id,
            context.lease.run_id,
            bad.id,
            bad.name,
            bad.arguments,
        )
        async with context.db.sessions() as session:
            assert await session.get(EffectReceiptRow, command.key) is None
            chart = await CloudChartRepository().get(session, context.owner_id, chart_id)
            assert chart.version == version and len(chart.payload["annotations"]) == 2
        # Caller scope and foreign receipt kinds cannot borrow an existing outcome.
        scope_call = ToolCall(
            id="command-0",
            name="chart_set_symbol",
            arguments={"chart_id": chart_id, "version": 1, "symbol": "EURUSDm"},
        )
        for invalid in (
            replace(context, owner_id="other-owner"),
            replace(context, agent_id="other-agent"),
            replace(context, thread_id="other-thread"),
        ):
            try:
                await registry.execute(scope_call, invalid)
            except LonoraError as error:
                assert error.code in {
                    "chart_command_scope_mismatch",
                    "agent_not_found",
                    "thread_not_found",
                }
            else:
                raise AssertionError("Cross-scope receipt accepted")
        collision = ToolCall(
            id="foreign-receipt",
            name="chart_set_timeframe",
            arguments={"chart_id": chart_id, "version": version, "timeframe": "4h"},
        )
        foreign = chart_state.chart_command(
            context.for_call(collision.id), collision.arguments, collision.name
        )
        async with context.db.sessions() as session, session.begin():
            session.add(
                EffectReceiptRow(
                    key=foreign.key,
                    result={
                        "kind": "financial",
                        "digest": foreign.digest,
                        "acknowledgment": {"fake": True},
                    },
                )
            )
        try:
            await registry.execute(collision, context)
        except LonoraError as error:
            assert error.code == "chart_command_identity_conflict"
        else:
            raise AssertionError("Foreign receipt replayed")
        # Real ToolLoop dies immediately after the atomic database commit.
        call = ToolCall(
            id="committed-before-death",
            name="chart_set_timeframe",
            arguments={"chart_id": chart_id, "version": version, "timeframe": "4h"},
        )
        await persist(
            context,
            {"environment": {"version": 1}},
            [
                ModelMessage(role="user", content="Change chart"),
                ModelMessage(role="assistant", content="", tool_calls=[call]),
            ],
            [call],
        )
        actual_update = chart_state.update_chart
        writes = 0

        async def commit_then_die(*args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal writes
            writes += 1
            await actual_update(*args, **kwargs)
            raise WorkerKilled()

        with patch.object(chart_state, "update_chart", commit_then_die):
            try:
                await execute_tool_loop(context, registry, 8)
            except WorkerKilled:
                pass
            else:
                raise AssertionError("Expected injected worker death")
        assert writes == 1
        # Owner changes the chart while worker is down. Replay must not undo it.
        async with context.db.sessions() as session, session.begin():
            chart = await CloudChartRepository().get(session, context.owner_id, chart_id)
            payload = {**chart.payload, "timeframe": "1d"}
            await CloudChartRepository().update(
                session, context.owner_id, chart_id, payload, chart.version
            )
        recovered = await fixture.lease(run)
        try:
            await registry.execute(call, context)
        except LonoraError as error:
            assert error.code == "stale_lease"
        else:
            raise AssertionError("Old worker replay accepted")

        async def model(*args: Any, **kwargs: Any) -> tuple[ModelReply, ModelSelection]:
            observation = json.loads(args[1][-1].content)
            assert observation["ok"] and observation["command"]["revision"] == version + 1
            assert observation["scene"] is None and observation["requires_scene_inspection"]
            return ModelReply(text="applied; current scene needs inspection"), ModelSelection(
                provider="openai", model="scripted"
            )

        with patch("lonora_agent.tool_loop.model_turn", model):
            outcome = await execute_tool_loop(recovered, registry, 8)
        assert outcome.text.startswith("applied") and writes == 1
        async with context.db.sessions() as session:
            chart = await CloudChartRepository().get(session, context.owner_id, chart_id)
            assert chart.version == version + 2 and chart.payload["timeframe"] == "1d"
            assert chart.payload["annotations"][0]["id"] == "manual"
            assert await session.scalar(select(func.count()).select_from(TradingJournalRow)) == 0
        print(
            "PASS five native command receipts, changed-intent rejection, invalid-batch rollback, real ToolLoop death/recovery, new fence, owner edit wins, zero trades"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
