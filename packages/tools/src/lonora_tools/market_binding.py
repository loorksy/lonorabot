from typing import Any, cast

from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import agent_binding, assert_payload_binding, same_binding
from lonora_db.schema import AgentRow, CloudChartRow, TradingGoalRow
from pydantic import BaseModel

from .context import ToolContext

MARKET_TOOLS = ("market_", "chart_", "watch_", "trade_", "goal_", "account_")


def market_tool(name: str) -> bool:
    return name.startswith(MARKET_TOOLS) or name == "list_accounts"


def align_payload(agent: AgentRow, payload: Any) -> Any:
    """Rewrite case-only differences onto the bound account and symbol."""
    if isinstance(payload, list):
        return [align_payload(agent, item) for item in cast(list[Any], payload)]
    if not isinstance(payload, dict):
        return payload
    aligned: dict[str, Any] = {}
    for key, value in cast(dict[str, Any], payload).items():
        if isinstance(value, (dict, list)):
            aligned[key] = align_payload(agent, value)
            continue
        if key == "account_id" and same_binding(value, agent.trading_account_id):
            aligned[key] = agent.trading_account_id
        elif key == "symbol" and same_binding(value, agent.trading_symbol):
            aligned[key] = agent.trading_symbol
        else:
            aligned[key] = value
    return aligned


def fill_bound_fields(agent: AgentRow, args: dict[str, Any], fields: set[str]) -> dict[str, Any]:
    filled = dict(args)
    if agent.trading_account_id and "account_id" in fields and not filled.get("account_id"):
        filled["account_id"] = agent.trading_account_id
    if agent.trading_symbol and "symbol" in fields and not filled.get("symbol"):
        filled["symbol"] = agent.trading_symbol
    return filled


async def prepare_market_arguments(
    context: ToolContext, name: str, args: dict[str, Any], model: type[BaseModel]
) -> dict[str, Any]:
    if not market_tool(name):
        return args
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        if not agent.trading_account_id or not agent.trading_symbol:
            return args
        aligned = align_payload(agent, args)
        if not isinstance(aligned, dict):
            return args
        return fill_bound_fields(agent, cast(dict[str, Any], aligned), set(model.model_fields))


async def guard_market_tool(
    context: ToolContext, name: str, args: dict[str, Any]
) -> dict[str, Any]:
    if not market_tool(name):
        return args
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        if not agent.trading_account_id:
            return args
        aligned = align_payload(agent, args)
        if isinstance(aligned, dict):
            args = cast(dict[str, Any], aligned)
        if name in {"watch_create", "trade_close_positions"} and not args.get("symbol"):
            args = {**args, "symbol": agent.trading_symbol}
        assert_payload_binding(agent, args)
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
        return args


def _kept(value: object, bound: str | None) -> bool:
    return same_binding(value, bound)


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
            result["symbols"] = [
                symbol
                for symbol in result.get("symbols", [])
                if _kept(symbol, agent.trading_symbol)
            ]
        if name == "market_instruments":
            result["instruments"] = [
                item
                for item in result.get("instruments", [])
                if _kept(item.get("symbol"), agent.trading_symbol)
            ]
        if name == "chart_list":
            result["charts"] = [
                item
                for item in result.get("charts", [])
                if _kept(item.get("account_id"), agent.trading_account_id)
                and _kept(item.get("symbol"), agent.trading_symbol)
            ]
        if name == "account_read":
            for key in ("positions", "orders"):
                result[key] = [
                    item
                    for item in result.get(key, [])
                    if _kept(item.get("symbol"), agent.trading_symbol)
                ]
        if name == "account_history":
            result["history"] = [
                item
                for item in result.get("history", [])
                if _kept(item.get("symbol"), agent.trading_symbol)
            ]
        if name == "list_accounts":
            result["accounts"] = [
                item
                for item in result.get("accounts", [])
                if _kept(item.get("connection_id"), agent.trading_account_id)
            ]
        return result
