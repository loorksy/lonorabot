from typing import Any, cast

from lonora_core.user_error import LonoraError
from lonora_db.agent_binding import (
    agent_binding,
    assert_payload_binding,
    fixed_market,
    flexible_scope,
    require_financial_agent,
    same_binding,
)
from lonora_db.runs import require_lease
from lonora_db.schema import AgentRow, CloudChartRow, TradingGoalRow
from pydantic import BaseModel

from .context import ToolContext

MARKET_TOOLS = ("market_", "chart_", "watch_", "trade_", "goal_", "account_")
# Reading records and narrowing admission need no financial authority: any agent may
# record an owner's restriction, and none can lift one.
NONFINANCIAL_TRADE_TOOLS = frozenset(
    {
        "trade_record_read",
        "trade_record_history",
        "trade_restriction_create",
        "trade_restriction_list",
    }
)


# Reading is open: a fixed-market agent reads every owned account and symbol (quotes,
# candles, accounts, full history and activity, records), like every other Agent. Its
# bound account and symbol stay its focus for every mutation path (charts, watches,
# goals, decisions, trades), and the executor independently re-checks the binding for
# every financial request. Copying market data into the agent's own workspace is a read
# of the market.
OPEN_READ_EFFECTS = frozenset({"market_candles_to_workspace"})


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
    if (
        agent.trading_symbol
        and "symbol" in fields
        and not filled.get("symbol")
        # An explicit every-symbol scope (trade_restriction_create) is not a missing symbol.
        and not filled.get("all_symbols")
        # The focus symbol belongs to the focus account: a call naming another owned
        # account reads (or is refused) for that account as a whole, fixed agents too.
        and ("account_id" not in fields or filled.get("account_id") == agent.trading_account_id)
    ):
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
        aligned = args if flexible_scope(agent) else align_payload(agent, args)
        if not isinstance(aligned, dict):
            return args
        return fill_bound_fields(agent, cast(dict[str, Any], aligned), set(model.model_fields))


async def guard_market_tool(
    context: ToolContext, name: str, args: dict[str, Any], *, read: bool = False
) -> dict[str, Any]:
    """Financial identity for financial tools; a fixed market for mutations only.

    ``read`` is the registry's own effect metadata for the tool: reads are open.
    """
    if not market_tool(name):
        return args
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        if (
            name.startswith("trade_")
            and name not in NONFINANCIAL_TRADE_TOOLS
            and agent.execution_mode != "shadow"
        ) or (
            name.startswith("goal_") and name not in {"goal_read", "goal_list", "goal_decisions"}
        ):
            run = await require_lease(session, context.lease)
            mode = (
                "shadow"
                if name.startswith("goal_") and run.model_metadata.get("execution_mode") == "shadow"
                else "live"
            )
            await require_financial_agent(
                session, context.owner_id, context.agent_id, execution_mode=mode
            )
        if not fixed_market(agent):
            return args
        aligned = align_payload(agent, args)
        if isinstance(aligned, dict):
            args = cast(dict[str, Any], aligned)
        if read or name in OPEN_READ_EFFECTS:
            return args
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


EXECUTION_SCOPE_NOTE = (
    "Reading is open across every owned account and symbol; charts, watches, goals, "
    "decisions and trades stay on this bound account and symbol."
)


def _kept(value: object, bound: str | None) -> bool:
    return same_binding(value, bound)


async def scope_market_result(
    context: ToolContext, name: str, result: dict[str, Any], args: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Annotate what a fixed-market agent may execute; never hide what it may read."""
    if name not in {"market_symbols", "market_instruments", "account_read", "list_accounts"}:
        return result
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        if not fixed_market(agent):
            return result
        result = dict(result)
        if name in {"market_symbols", "market_instruments", "account_read"}:
            # The bound account's catalog and exposure are readable; trading is not widened.
            result["execution_scope"] = {
                "account_id": agent.trading_account_id,
                "symbol": agent.trading_symbol,
                "note": EXECUTION_SCOPE_NOTE,
            }
        if name == "account_read":
            bound = _kept((args or {}).get("account_id"), agent.trading_account_id)
            for key in ("positions", "orders"):
                result[key] = [
                    {
                        **item,
                        "in_execution_scope": bound
                        and _kept(item.get("symbol"), agent.trading_symbol),
                    }
                    for item in result.get(key, [])
                ]
        if name == "list_accounts":
            result["accounts"] = [
                {
                    **item,
                    "in_execution_scope": _kept(
                        item.get("connection_id"), agent.trading_account_id
                    ),
                }
                for item in result.get("accounts", [])
            ]
        return result
