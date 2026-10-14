from typing import Any

from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import agent_binding, assert_payload_binding
from lonora_db.schema import CloudChartRow, TradingGoalRow

from .context import ToolContext

MARKET_TOOLS = ("market_", "chart_", "watch_", "trade_", "goal_", "account_")


async def guard_market_tool(
    context: ToolContext, name: str, args: dict[str, Any]
) -> dict[str, Any]:
    if not name.startswith(MARKET_TOOLS) and name != "list_accounts":
        return args
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        if not agent.trading_account_id:
            return args
        assert_payload_binding(agent, args)
        if name == "watch_create" and not args.get("symbol"):
            args = {**args, "symbol": agent.trading_symbol}
        if args.get("chart_id"):
            chart = await session.get(CloudChartRow, args["chart_id"])
            if chart is None or chart.owner_id != context.owner_id:
                raise LonoraError("cloud_charts_not_found", 404)
            assert_payload_binding(agent, chart.payload)
        if args.get("goal_id"):
            goal = await session.get(TradingGoalRow, args["goal_id"])
            if goal is None or goal.owner_id != context.owner_id:
                raise LonoraError("goal_not_found", 404)
            assert_payload_binding(agent, goal.payload)
        if name == "watch_create" and args.get("position_id"):
            broker = await context.brokers.get(context.owner_id, str(agent.trading_account_id))
            position = next(
                (item for item in await broker.positions() if item.id == args["position_id"]), None
            )
            if position is None:
                raise LonoraError("position_not_found", 404)
            assert_payload_binding(agent, {"symbol": position.symbol})
        if name == "trade_close_positions" and args.get("symbol") is None:
            args = {**args, "symbol": agent.trading_symbol}
        return args


async def scope_market_result(
    context: ToolContext, name: str, result: dict[str, Any]
) -> dict[str, Any]:
    if name not in {
        "market_symbols",
        "market_instruments",
        "chart_list",
        "account_read",
        "account_history",
        "list_accounts",
    }:
        return result
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        if not agent.trading_account_id:
            return result
        result = dict(result)
        if name == "market_symbols":
            result["symbols"] = [s for s in result.get("symbols", []) if s == agent.trading_symbol]
        if name == "market_instruments":
            result["instruments"] = [
                i for i in result.get("instruments", []) if i.get("symbol") == agent.trading_symbol
            ]
        if name == "chart_list":
            result["charts"] = [
                c
                for c in result.get("charts", [])
                if c.get("account_id") == agent.trading_account_id
                and c.get("symbol") == agent.trading_symbol
            ]
        if name == "account_read":
            for key in ("positions", "orders"):
                result[key] = [
                    item
                    for item in result.get(key, [])
                    if item.get("symbol") == agent.trading_symbol
                ]
        if name == "account_history":
            result["history"] = [
                item
                for item in result.get("history", [])
                if item.get("symbol") == agent.trading_symbol
            ]
        if name == "list_accounts":
            result["accounts"] = [
                item
                for item in result.get("accounts", [])
                if item.get("connection_id") == agent.trading_account_id
            ]
        return result
