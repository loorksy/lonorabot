"""Invalid Goal schema repairs inside one existing Run; only a real pending card is proposed."""

import asyncio
import json
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_db.schema import (
    AgentRow,
    BrokerSessionRow,
    MessageRow,
    RunRow,
    SuperBotRequestRow,
    TradingGoalRow,
    TradingJournalRow,
)
from lonora_tools.loader import load_tools
from sqlalchemy import func, select


async def main():
    f = await Fixture().open()
    try:
        account = (
            await f.request(
                "POST",
                "/trading/connections",
                {
                    "provider": "simulation",
                    "account_id": "conversational-setup",
                    "enabled": True,
                },
            )
        )["id"]
        agent = await f.agent("Natural-language Super Bot setup")
        async with f.runtime.db.sessions() as s, s.begin():
            row = await s.get(AgentRow, agent["id"])
            assert row
            row.role, row.trading_account_id, row.trading_symbol = "specialist", account, "XAUUSDm"
        thread = await f.conversation(agent)
        context = await f.lease(await f.run(agent, thread))
        base = {
            "title": "Review gold",
            "objective": "Prepare a supervised market review",
            "account_id": account,
            "symbol": "XAUUSDm",
        }
        phase = 0
        goal_id = ""

        async def complete(
            capability: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any
        ):
            nonlocal phase, goal_id
            if phase == 0:
                assert "Do not require ritual phrases" in messages[0].content
                call = ToolCall(
                    id="invalid-watch",
                    name="goal_create",
                    arguments={
                        **base,
                        "steps": [{"id": "observe", "title": "Observe market", "kind": "watch"}],
                    },
                )
            elif phase == 1:
                observation = next(
                    message
                    for message in messages
                    if message.role == "tool" and message.tool_call_id == "invalid-watch"
                )
                error = json.loads(observation.content)
                assert error["code"] == "tool_arguments_invalid" and error["retryable"]
                assert error["issues"] == [
                    {
                        "path": ["steps", 0],
                        "type": "value_error",
                        "code": "goal_watch_condition_required",
                    }
                ]
                call = ToolCall(
                    id="repaired-goal",
                    name="goal_create",
                    arguments={
                        **base,
                        "steps": [
                            {
                                "id": "review",
                                "title": "Review current market evidence",
                                "kind": "review",
                                "review_interval_seconds": 900,
                            }
                        ],
                    },
                )
            elif phase == 2:
                observation = next(
                    message
                    for message in messages
                    if message.role == "tool" and message.tool_call_id == "repaired-goal"
                )
                saved = json.loads(observation.content)
                assert saved["ok"] and saved["payload"]["steps"][0]["kind"] == "review"
                goal_id = saved["id"]
                call = ToolCall(
                    id="prepare-card",
                    name="super_bot_propose",
                    arguments={"goal_id": goal_id, "mode": "supervised"},
                )
            else:
                observation = next(
                    message
                    for message in messages
                    if message.role == "tool" and message.tool_call_id == "prepare-card"
                )
                proposal = json.loads(observation.content)
                assert proposal["ok"] and proposal["status"] == "pending"
                assert proposal["internal_ids_are_private"] is True
                assert "لم يُفعّل التداول التلقائي" in proposal["owner_summary"]
                return ModelReply(text=proposal["owner_summary"]), ModelSelection(
                    provider="openai", model="scripted-setup-fixture"
                )
            phase += 1
            return ModelReply(tool_calls=[call]), ModelSelection(
                provider="openai", model="scripted-setup-fixture"
            )

        with patch.object(context.router, "complete", complete):
            await execute_run(context, load_tools(), 120, 6)
        async with f.runtime.db.sessions() as s:
            run = await s.get(RunRow, context.lease.run_id)
            assert run and run.status == "completed" and phase == 3
            answer = await s.scalar(
                select(MessageRow)
                .where(MessageRow.thread_id == thread["id"], MessageRow.role == "assistant")
                .order_by(MessageRow.seq.desc())
                .limit(1)
            )
            assert answer and goal_id not in answer.content and "pending" not in answer.content
            assert "بطاقة" not in answer.content and "لم يُفعّل التداول التلقائي" in answer.content
            assert await s.scalar(select(func.count()).select_from(TradingGoalRow)) == 1
            row = await s.scalar(
                select(SuperBotRequestRow).where(SuperBotRequestRow.goal_id == goal_id)
            )
            assert row and row.status == "pending" and row.mode == "supervised"
            goal = await s.get(TradingGoalRow, goal_id)
            assert goal and not goal.state.get("autonomous")
            assert await s.scalar(select(func.count()).select_from(TradingJournalRow)) == 0
        async with f.runtime.db.sessions() as s, s.begin():
            broker = await s.get(BrokerSessionRow, account)
            assert broker
            broker.state = {
                **broker.state,
                "broker_recovery": {
                    "status": "degraded",
                    "reason_code": "broker_reconciliation_pending",
                    "observed_at": utcnow().isoformat(),
                },
            }
        live = await f.request("GET", f"/agents/{agent['id']}/state")
        assert live["health"][0]["kind"] == "broker"
        assert live["health"][0]["reason_code"] == "broker_reconciliation_pending"
        assert not any(item.get("kind") == "market" for item in live["health"])
        print(
            "PASS same normal AgentRuntime repairs exact field validation and creates one real supervised card without a second user message, price fabrication, authority grant or trade"
        )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
