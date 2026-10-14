"""Real ordinary-agent/tool-loop/DB integration; scripted model and imported simulation only."""

import asyncio
import json
from datetime import timedelta
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_db.schema import RunRow, TradingAccountRow, TradingJournalRow
from lonora_tools.loader import load_tools


async def main() -> None:
    fixture = await Fixture().open()
    connection_id = None
    chart_id = None
    try:
        agent = await fixture.agent("Ordinary persistent agent fixture")
        thread = await fixture.conversation(agent)
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
        )
        connection_id = connection["id"]
        symbol = "XAUUSDm"
        candle = {
            "symbol": symbol,
            "timeframe": "1h",
            "open": "2700",
            "high": "2704",
            "low": "2699",
            "close": "2701",
        }
        await fixture.request(
            "POST",
            f"/trading/connections/{connection_id}/simulation",
            {
                "snapshot": {
                    "balance": "10000",
                    "currency": "USD",
                    "instruments": [
                        {
                            "symbol": symbol,
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.01",
                            "volume_max": "10",
                            "volume_step": "0.01",
                        }
                    ],
                    "quotes": {
                        symbol: {
                            "symbol": symbol,
                            "bid": "2700",
                            "ask": "2701",
                            "observed_at": utcnow().isoformat(),
                            "source": "explicit-simulation-fixture",
                        }
                    },
                    "candles": {
                        symbol + ":1h": [
                            {**candle, "time": (utcnow() - timedelta(hours=35 - i)).isoformat()}
                            for i in range(35)
                        ]
                    },
                }
            },
        )
        await fixture.request(
            "PUT", "/trading/controls", {"enabled": True, "emergency_stop": False}
        )
        run = await fixture.run(agent, thread)
        context = await fixture.lease(run)
        phase = 0
        operation_id = None

        async def complete(
            capability: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any
        ):
            nonlocal phase, chart_id, operation_id
            phase += 1
            result: ModelReply
            if phase == 1:
                result = ModelReply(
                    tool_calls=[ToolCall(id="discover", name="list_accounts", arguments={})]
                )
            elif phase == 2:
                previous = json.loads(messages[-1].content)
                assert connection_id in {item["connection_id"] for item in previous["accounts"]}
                result = ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="symbols",
                            name="market_symbols",
                            arguments={"account_id": connection_id},
                        ),
                        ToolCall(
                            id="spec",
                            name="market_instrument",
                            arguments={"account_id": connection_id, "symbol": symbol},
                        ),
                    ]
                )
            elif phase == 3:
                result = ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="open",
                            name="chart_open",
                            arguments={
                                "account_id": connection_id,
                                "symbol": symbol,
                                "indicators": [{"name": "rsi", "period": 14}],
                            },
                        )
                    ]
                )
            elif phase == 4:
                previous = json.loads(messages[-1].content)
                chart_id = previous["chart"]["id"]
                assert previous["scene"]["symbol"] == symbol
                result = ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="image", name="chart_snapshot", arguments={"chart_id": chart_id}
                        ),
                        ToolCall(
                            id="trade",
                            name="trade_execute",
                            arguments={
                                "account_id": connection_id,
                                "symbol": symbol,
                                "action": "buy",
                                "volume": "0.1",
                            },
                        ),
                    ]
                )
            elif phase == 5:
                previous = json.loads(messages[-1].content)
                assert previous["status"] == "confirmed", previous
                operation_id = previous["operation_id"]
                result = ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="account",
                            name="account_read",
                            arguments={"account_id": connection_id},
                        )
                    ]
                )
            else:
                previous = json.loads(messages[-1].content)
                assert previous["positions"][0]["symbol"] == symbol
                result = ModelReply(
                    text="Explicit scripted fixture: persistent chart, snapshot and simulated trade completed."
                )
            return result, ModelSelection(
                provider="openai", model="explicit-scripted-market-fixture"
            )

        with patch.object(context.router, "complete", complete):
            await execute_run(context, load_tools(), 120, 12)
            waiting = await fixture.request("GET", "/runs/" + run["id"])
            assert waiting["status"] == "waiting_input"
            approvals = cast(
                list[dict[str, Any]],
                await fixture.request("GET", f"/trading/approvals?thread_id={thread['id']}"),
            )
            approval = next(card for card in approvals if card["run_id"] == run["id"])
            assert approval["status"] == "pending"
            broker = await context.brokers.get(context.owner_id, connection_id)
            assert not await broker.positions()
            await fixture.request(
                "POST", f"/trading/approvals/{approval['id']}/decision", {"decision": "approve"}
            )
            assert not await broker.positions()
            context = await fixture.lease(run)
            await execute_run(context, load_tools(), 120, 12)
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(RunRow, run["id"])
            assert (
                row and row.status == "completed" and row.result and "simulated trade" in row.result
            )
            journal = await session.get(TradingJournalRow, operation_id)
            assert (
                journal
                and journal.status == "confirmed"
                and journal.result["details"]["execution"]["run_id"] == run["id"]
            )
        messages = await fixture.request("GET", f"/threads/{thread['id']}/messages")
        assert any(
            "persistent chart" in message["content"]
            for message in cast(list[dict[str, Any]], messages)
        )
        print(
            "PASS ordinary agent: message/run → global router → account/market/chart/image/trade tools → durable journal/result/events"
        )
    finally:
        if chart_id:
            await fixture.request("DELETE", "/charts/" + chart_id)
        if connection_id:
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(TradingAccountRow, connection_id)
                if row:
                    await session.delete(row)
            await fixture.request("DELETE", "/trading/connections/" + connection_id)
        await fixture.request(
            "PUT", "/trading/controls", {"enabled": False, "emergency_stop": False}
        )
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
