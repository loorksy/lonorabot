"""Invalid Goal schema repairs inside one existing Run; only a real pending grant card is proposed."""

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
    OwnerActionRow,
    RunRow,
    TradingGoalRow,
    TradingJournalRow,
)
from lonora_tools.loader import load_tools
from sqlalchemy import func, select

SUMMARY = "جهّزت خطة المراجعة وبطاقة التفويض؛ لن أتداول بنفسي قبل أن توقّعها بمفتاح المرور."


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
        # The grant card suggests a daily loss from the account's actual equity.
        await f.request(
            "POST",
            f"/trading/connections/{account}/simulation",
            {
                "snapshot": {
                    "balance": "5000",
                    "equity": "5000",
                    "currency": "USD",
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
                    "positions": [],
                    "orders": [],
                }
            },
        )
        agent = await f.agent("Natural-language trading setup")
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
                # Trading on its own is one grant card the owner signs, never a goal flag.
                call = ToolCall(
                    id="prepare-card",
                    name="owner_action_propose",
                    arguments={"kind": "grant_authority"},
                )
            else:
                observation = next(
                    message
                    for message in messages
                    if message.role == "tool" and message.tool_call_id == "prepare-card"
                )
                proposal = json.loads(observation.content)
                assert proposal["ok"] and proposal["passkey_required"] is True, proposal
                assert proposal["execution_authorized"] is False
                return ModelReply(text=SUMMARY), ModelSelection(
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
            assert answer.content == SUMMARY
            assert await s.scalar(select(func.count()).select_from(TradingGoalRow)) == 1
            card = await s.scalar(
                select(OwnerActionRow).where(
                    OwnerActionRow.thread_id == thread["id"],
                    OwnerActionRow.kind == "grant_authority",
                )
            )
            assert card and card.status == "pending"
            goal = await s.get(TradingGoalRow, goal_id)
            assert goal and "autonomous" not in goal.state
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
            "PASS same normal AgentRuntime repairs exact field validation and proposes one real grant card without a second user message, price fabrication, authority grant or trade"
        )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
