"""A sizing estimate is read-only and never creates an execution proposal."""

from typing import Any

from lonora_contracts.position_sizing import PositionSizingRequest
from lonora_db.agent_binding import agent_binding, assert_market_binding
from lonora_trading.position_sizing import position_size

from .base import Tool
from .context import ToolContext


async def size(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    request = PositionSizingRequest.model_validate(args)
    async with context.db.sessions() as session:
        agent = await agent_binding(session, context.owner_id, context.agent_id)
        assert_market_binding(agent, request.account_id, request.symbol)
    broker = await context.brokers.get(context.owner_id, request.account_id)
    return (await position_size(broker, request)).model_dump(mode="json")


def tools() -> list[Tool]:
    return [
        Tool(
            "market_position_size",
            "Estimate a broker-valid market volume from a risk budget and explicit stop loss "
            "using fresh exact-symbol broker tick values. Currency must exactly match the "
            "broker account currency, including cent units; no FX conversion. The estimate "
            "includes spread but excludes gaps, slippage, commissions, swap and margin "
            "validation. It is not a maximum-loss guarantee and authorizes no execution.",
            PositionSizingRequest,
            size,
            read_only=True,
        )
    ]
