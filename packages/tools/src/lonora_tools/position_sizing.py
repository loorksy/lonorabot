"""A sizing estimate is read-only and never creates an execution proposal."""

from typing import Any

from lonora_contracts.position_sizing import PositionSizingRequest
from lonora_trading.position_sizing import position_size

from .base import Tool
from .context import ToolContext
from .symbols import order_symbol


async def size(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    request = PositionSizingRequest.model_validate(args)
    # An estimate is a read: any owned account and symbol (the broker lookup checks ownership).
    broker = await context.brokers.get(context.owner_id, request.account_id)
    request = request.model_copy(update={"symbol": await order_symbol(broker, request.symbol)})
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
