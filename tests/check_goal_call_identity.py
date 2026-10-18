"""Freeze optional current-step intent before execution; checkpoint replay cannot advance it."""

import asyncio
import copy
from unittest.mock import AsyncMock, patch

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_db.schema import GoalDecisionRow, TradingGoalRow
from lonora_session.idempotency import stable_id
from lonora_tools.loader import load_tools


async def main() -> None:
    f = await Fixture().open()
    try:
        account = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": "goal-call-identity", "enabled": True},
            )
        )["id"]
        agent = await f.agent("Frozen Goal call")
        await f.request(
            "PUT", f"/agents/{agent['id']}/execution-mode", {"execution_mode": "shadow"}
        )
        thread = await f.conversation(agent)
        context = await f.lease(await f.run(agent, thread))
        registry = load_tools()
        goal = await registry.execute(
            ToolCall(
                id="create",
                name="goal_create",
                arguments={
                    "title": "Two separate actions",
                    "objective": "Do not replay the next action after a checkpoint gap",
                    "account_id": account,
                    "symbol": "EURUSDm",
                    "maximum_volume": "0.1",
                    "max_trade_actions": 2,
                    "steps": [
                        {
                            "id": name,
                            "title": name,
                            "kind": "trade",
                            "trade": {
                                "account_id": account,
                                "symbol": "EURUSDm",
                                "action": "buy",
                                "volume": "0.1",
                            },
                        }
                        for name in ("first", "second")
                    ],
                },
            ),
            context,
        )
        call = ToolCall(
            id="fixed-effect",
            name="goal_step_execute",
            arguments={"goal_id": goal["id"], "note": "Execute the current action once"},
        )
        operation_id = stable_id(goal["id"], "step:first:attempt:1")
        broker_result = {
            "operation_id": operation_id,
            "status": "confirmed",
            "code": "explicit-fixture-receipt",
        }
        # Inject at the domain boundary; the separate Shadow Goal suite exercises
        # real virtual execution. Here the crash gap and moved plan are isolated.
        execute = AsyncMock(return_value={"operation_id": operation_id, "result": broker_result})
        with patch("lonora_tools.trading_goal.execute_goal_step", execute):
            initial = await registry.execute(call, context)
            assert initial["operation_id"] == operation_id
            assert execute.await_args and execute.await_args.args[5] == "first"
            async with f.runtime.db.sessions() as session, session.begin():
                row = await session.get(TradingGoalRow, goal["id"], with_for_update=True)
                assert row
                state = copy.deepcopy(row.state)
                state["steps"]["first"]["status"], state["current_step"] = "completed", "second"
                row.state = state
                session.add(
                    GoalDecisionRow(
                        id=stable_id(row.id, "decision:first:attempt:1"),
                        goal_id=row.id,
                        owner_id=f.owner,
                        step_id="first",
                        run_id=context.lease.run_id,
                        operation_id=operation_id,
                        status="confirmed",
                        result=broker_result,
                    )
                )
            replay = await registry.execute(call, context)
            assert replay["deduplicated"] and replay["operation_id"] == operation_id
            assert execute.await_count == 1
            async with f.runtime.db.sessions() as session:
                row = await session.get(TradingGoalRow, goal["id"])
                assert (
                    row
                    and row.state["current_step"] == "second"
                    and row.state["steps"]["second"]["status"] == "pending"
                )
        print(
            "PASS optional current-step call is durably frozen; replay after first completion returns the original decision and cannot execute the next step"
        )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
