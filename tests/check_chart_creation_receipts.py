"""Native creation identity, real read preparation and same-Run crash recovery."""

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.tool_loop import execute_tool_loop, persist
from lonora_charts import state as chart_state
from lonora_contracts.chart import ChartState
from lonora_contracts.model_routing import ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.cloud_charts import CloudChartRepository
from lonora_db.schema import CloudChartRow, TradingJournalRow
from lonora_tools import chart as chart_tools
from lonora_tools.loader import load_tools
from sqlalchemy import func, select


class WorkerKilled(BaseException):
    pass


async def main() -> None:
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Creation receipt verification")
        thread = await fixture.conversation(agent)
        run = await fixture.run(agent, thread)
        context = await fixture.lease(run)
        registry = load_tools()
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": "creation-" + uuid4().hex,
                "enabled": True,
            },
        )
        markets = [
            ("EURUSDm", "5m", 5),
            ("XAUUSDm", "15m", 15),
            ("XAUUSDm", "1h", 60),
            ("US500.cash", "4h", 240),
            ("BTCUSD#", "1d", 1440),
        ]
        candles = {
            symbol + ":" + timeframe: [
                {
                    "symbol": symbol,
                    "timeframe": timeframe,
                    "time": (
                        datetime(2026, 10, 1, tzinfo=UTC) + timedelta(minutes=index * minutes)
                    ).isoformat(),
                    "open": str(100 + index),
                    "high": str(104 + index),
                    "low": str(99 + index),
                    "close": str(102 + index),
                }
                for index in range(60)
            ]
            for symbol, timeframe, minutes in markets
        }
        await fixture.request(
            "POST",
            "/trading/connections/" + connection["id"] + "/simulation",
            {"snapshot": {"balance": "10000", "currency": "USD", "candles": candles}},
        )
        refreshes: list[str] = []
        actual_refresh = chart_state.refresh_chart

        async def refresh(*args: Any, **kwargs: Any) -> bool:
            refreshes.append(args[3])
            return await actual_refresh(*args, **kwargs)

        original_create = chart_tools.create_chart
        commits = 0

        async def commit_then_die(*args: Any, **kwargs: Any) -> dict[str, Any]:
            nonlocal commits
            commits += 1
            await original_create(*args, **kwargs)
            raise WorkerKilled()

        call = ToolCall(
            id="open-before-death",
            name="chart_open",
            arguments={
                "account_id": connection["id"],
                "symbol": "XAUUSDm",
                "timeframe": "15m",
                "annotations": [{"type": "price", "price": 101}],
            },
        )
        await persist(
            context,
            {"environment": {"version": 1}},
            [
                ModelMessage(role="user", content="Open a chart then inspect it"),
                ModelMessage(role="assistant", content="", tool_calls=[call]),
            ],
            [call],
        )
        with (
            patch.object(chart_tools, "create_chart", commit_then_die),
            patch.object(chart_state, "refresh_chart", refresh),
        ):
            try:
                await execute_tool_loop(context, registry, 8)
            except WorkerKilled:
                pass
            else:
                raise AssertionError("Expected worker death after creation commit")
        chart_id = context.for_call(call.id).resource_id
        assert commits == 1 and refreshes == []
        async with context.db.sessions() as session, session.begin():
            row = await CloudChartRepository().get(session, context.owner_id, chart_id)
            assert row.version == 1
            await CloudChartRepository().update(
                session,
                context.owner_id,
                chart_id,
                {
                    **row.payload,
                    "timeframe": "1h",
                    "annotations": [{"type": "price", "price": 123, "id": "owner"}],
                },
                row.version,
            )
        recovered = await fixture.lease(run)
        seen: dict[str, Any] = {}

        async def model(*args: Any, **kwargs: Any) -> tuple[ModelReply, ModelSelection]:
            import json

            seen.update(json.loads(args[1][-1].content))
            return ModelReply(text="Created; inspect current scene separately"), ModelSelection(
                provider="openai", model="scripted"
            )

        with (
            patch("lonora_agent.tool_loop.model_turn", model),
            patch.object(chart_state, "refresh_chart", refresh),
        ):
            await execute_tool_loop(recovered, registry, 8)
            replay = await registry.execute(call, recovered)
        assert seen["chart"] == replay["chart"]
        assert replay["chart"]["version"] == 1 and replay["chart"]["payload"]["timeframe"] == "15m"
        assert replay["scene"] is None and replay["requires_scene_inspection"]
        assert commits == 1 and refreshes == []
        # Explicit current read materializes latest configuration, preserving the owner edit.
        inspected = await registry.execute(
            ToolCall(id="inspect", name="chart_inspect", arguments={"chart_id": chart_id}),
            recovered,
        )
        assert inspected["chart"]["version"] == 2 and inspected["scene"]["timeframe"] == "1h"
        assert inspected["scene"]["annotations"][0]["id"] == "owner"
        changed = call.model_copy(update={"arguments": {**call.arguments, "symbol": "EURUSDm"}})
        try:
            await registry.execute(changed, recovered)
        except LonoraError as error:
            assert error.code == "chart_command_identity_conflict"
        else:
            raise AssertionError("Changed creation intent accepted")
        try:
            await registry.execute(call, context)
        except LonoraError as error:
            assert error.code == "stale_lease"
        else:
            raise AssertionError("Stale creator accepted")
        # Existing unreceipted rows must not be blessed using their current owner-edited payload.
        legacy = ToolCall(id="legacy-open", name="chart_open", arguments=call.arguments)
        async with context.db.sessions() as session, session.begin():
            await CloudChartRepository().create(
                session,
                context.owner_id,
                ChartState.model_validate(call.arguments).model_dump(mode="json"),
                agent_id=context.agent_id,
                thread_id=context.thread_id,
                resource_id=recovered.for_call(legacy.id).resource_id,
            )
        try:
            await registry.execute(legacy, recovered)
        except LonoraError as error:
            assert error.code == "chart_creation_receipt_missing"
        else:
            raise AssertionError("Unreceipted creation falsely acknowledged")
        # Native open -> immediate snapshot works without gateway ticks or test-side refresh.
        for index, (symbol, timeframe) in enumerate(
            [
                ("EURUSDm", "5m"),
                ("XAUUSDm", "15m"),
                ("US500.cash", "4h"),
                ("BTCUSD#", "1d"),
            ]
        ):
            request = ToolCall(
                id=f"market-{index}",
                name="chart_open",
                arguments={
                    "account_id": connection["id"],
                    "symbol": symbol,
                    "timeframe": timeframe,
                },
            )
            first, duplicate = await asyncio.gather(
                registry.execute(request, recovered), registry.execute(request, recovered)
            )
            assert first == duplicate and first["chart"]["payload"]["symbol"] == symbol
            assert first["scene"] is None
            artifact = await registry.execute(
                ToolCall(
                    id=f"snapshot-{index}",
                    name="chart_snapshot",
                    arguments={"chart_id": first["chart"]["id"]},
                ),
                recovered,
            )
            assert artifact["chart_snapshot"]["symbol"] == symbol
            assert artifact["chart_snapshot"]["timeframe"] == timeframe
            assert artifact["chart_snapshot"]["source"] == "saved_semantic_scene"
        async with context.db.sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(CloudChartRow)
                    .where(CloudChartRow.agent_id == agent["id"])
                )
                == 6
            )
            assert await session.scalar(select(func.count()).select_from(TradingJournalRow)) == 0
        print(
            "PASS atomic creation intent/ack, worker death/new fence, owner edit priority, legacy uncertainty, four-market immediate native snapshots, concurrent replay and zero trades"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
