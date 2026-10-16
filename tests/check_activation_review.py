"""Signed activation resumes into the existing observe-only work lane exactly once."""

import asyncio
import json
from decimal import Decimal
from typing import Any
from unittest.mock import patch

from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.collaboration.outcome_return import return_pending_outcomes
from lonora_agent.executor import execute_run
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.activation_review import dispatch_activation_reviews
from lonora_db.runs import claim_next, run_data
from lonora_db.schema import MessageRow, TradingGoalRow, TradingJournalRow
from lonora_gateway.scheduler import scheduler_tick
from lonora_tools.loader import load_tools
from sqlalchemy import func, select


async def main():
    f = await Fixture().open()
    try:
        account = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": "activation-review", "enabled": True},
            )
        )["id"]
        await f.request(
            "POST",
            f"/trading/connections/{account}/simulation",
            {
                "snapshot": {
                    "balance": "2500",
                    "currency": "USD",
                    "instruments": [],
                    "quotes": {},
                    "positions": [],
                    "orders": [],
                }
            },
        )
        agent = await f.agent("Activation review")
        thread = await f.conversation(agent)
        goal = await f.request(
            "POST",
            "/trading/goals",
            {
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "account_id": account,
                "symbol": "EURUSDm",
                "title": "Review before action",
                "objective": "Inspect actual state first",
                "maximum_volume": "0.1",
                "max_trade_actions": 1,
                "steps": [{"id": "inspect", "title": "Read actual evidence", "kind": "analysis"}],
            },
        )
        assert await scheduler_tick(f.runtime.db) == 0
        device = await Device.enroll(f)
        await device.authorize_goal_service(f, goal)
        counts = await asyncio.gather(scheduler_tick(f.runtime.db), scheduler_tick(f.runtime.db))
        assert sum(counts) == 1 and await dispatch_activation_reviews(f.runtime.db) == 0
        async with f.runtime.db.sessions() as session, session.begin():
            assert await claim_next(session, "activation-test", 120, lane="conversation") is None
            row = await claim_next(session, "activation-test", 120, lane="work")
            assert row and row.trigger == "activation" and row.thread_id != thread["id"]
            data = run_data(row)
        context = await f.lease(data)
        # Even a direct executor caller cannot spend this signed goal's authority
        # from the observe-only activation review.
        try:
            await context.trading.execute(
                f.owner,
                TradeRequest(
                    operation_id="activation-must-not-trade",
                    account_id=account,
                    symbol="EURUSDm",
                    action="buy",
                    volume=Decimal("0.1"),
                ),
                context.lease,
            )
        except LonoraError as error:
            assert error.code == "observe_only_execution_forbidden"
        else:
            raise AssertionError("activation directly mutated the broker")
        phase = 0

        async def complete(
            capability: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any
        ):
            nonlocal phase
            assert capability == Capability.BACKGROUND
            assert "trade_execute" not in {tool.name for tool in tools}
            phase += 1
            if phase == 1:
                reply = ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="activation-read-goal",
                            name="goal_read",
                            arguments={"goal_id": goal["id"]},
                        )
                    ]
                )
            elif phase == 2:
                result = json.loads(messages[-1].content)
                assert (
                    result["ok"] is True
                    and result["id"] == goal["id"]
                    and result["step"]["id"] == "inspect"
                )
                reply = ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="activation-connections",
                            name="account_read",
                            arguments={"account_id": account},
                        )
                    ]
                )
            else:
                result = json.loads(messages[-1].content)
                assert result["ok"] is True and result["account"]["balance"] == "2500"
                reply = ModelReply(
                    text="Reviewed the saved goal and configured broker account. Waiting for current market evidence; no trade was sent."
                )
            return reply, ModelSelection(provider="openai", model="scripted-activation-review")

        with patch.object(context.router, "complete", complete):
            await execute_run(context, load_tools(), 120, 5)
        await return_pending_outcomes(f.runtime.db)
        await return_pending_outcomes(f.runtime.db)
        async with f.runtime.db.sessions() as session:
            replies = list(
                await session.scalars(
                    select(MessageRow).where(
                        MessageRow.thread_id == thread["id"], MessageRow.role == "assistant"
                    )
                )
            )
            assert len(replies) == 1 and "no trade was sent" in replies[0].content
            assert await session.scalar(select(func.count()).select_from(TradingJournalRow)) == 0
        assert await scheduler_tick(f.runtime.db) == 0
        second = await f.request(
            "POST",
            "/trading/goals",
            {
                **goal["payload"],
                "agent_id": agent["id"],
                "thread_id": thread["id"],
                "title": "Unconfigured review",
            },
        )
        await device.authorize_goal_service(f, second)
        assert await scheduler_tick(f.runtime.db) == 1
        async with f.runtime.db.sessions() as session, session.begin():
            row = await claim_next(session, "activation-test", 120, lane="work")
            assert row
            data = run_data(row)
        failed_context = await f.lease(data)

        async def unavailable(*args: Any, **kwargs: Any):
            raise LonoraError("model_not_configured", 409)

        with patch.object(failed_context.router, "complete", unavailable):
            await execute_run(failed_context, load_tools(), 120, 5)
        live = await f.request("GET", f"/agents/{agent['id']}/state")
        assert (
            live["state"] == "action_required" and live["reason_code"] == "activation_review_failed"
        )
        assert live["super_bot"][0]["review_error_code"] == "model_not_configured"
        assert await scheduler_tick(f.runtime.db) == 0  # No paid-model retry loop.

        peer = await f.agent("Review peer")
        group = await f.request(
            "POST",
            "/groups/create",
            {
                "name": "Activation group",
                "member_ids": [agent["id"], peer["id"]],
                "participation": "mentions_or_lead",
            },
        )
        f.groups.append(group["id"])
        f.group_threads.append(group["thread_id"])
        goal = await f.request(
            "POST",
            "/trading/goals",
            {
                **goal["payload"],
                "agent_id": agent["id"],
                "thread_id": group["thread_id"],
                "title": "Inspect a blocked group goal",
            },
        )
        async with f.runtime.db.sessions() as session, session.begin():
            blocked = await session.get(TradingGoalRow, goal["id"])
            assert blocked
            blocked.state = {
                **blocked.state,
                "status": "blocked",
                "code": "market_evidence_unavailable",
            }
        await device.authorize_goal_service(f, goal)
        assert await scheduler_tick(f.runtime.db) == 1
        async with f.runtime.db.sessions() as session, session.begin():
            row = await claim_next(session, "activation-test", 120, lane="work")
            assert row
            data = run_data(row)
        group_context = await f.lease(data)
        phase = 0
        with patch.object(group_context.router, "complete", complete):
            await execute_run(group_context, load_tools(), 120, 5)
        await return_pending_outcomes(f.runtime.db)
        async with f.runtime.db.sessions() as session:
            replies = list(
                await session.scalars(
                    select(MessageRow).where(
                        MessageRow.thread_id == group["thread_id"], MessageRow.role == "assistant"
                    )
                )
            )
            assert len(replies) == 1 and replies[0].agent_id == agent["id"]
            blocked = await session.get(TradingGoalRow, goal["id"])
            assert blocked and blocked.state["status"] == "blocked"  # Read-only does not resume it.
            assert await session.scalar(select(func.count()).select_from(TradingJournalRow)) == 0
        print(
            "PASS verified activation schedules one restart-safe observe-only background review; normal AgentRuntime reads the same Goal, cannot execute, and returns one actual result to its conversation"
        )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
