from typing import Any

from lonora_charts.indicators import indicator_series
from lonora_market.broker import broker_market
from pydantic import Field

from .base import Tool
from .context import ToolContext
from .market import CandlesInput
from .symbols import canonical_broker_symbol


class IndicatorInput(CandlesInput):
    name: str
    period: int = Field(default=14, ge=2, le=500)


async def calculate(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    broker = await context.brokers.get(context.owner_id, args["account_id"])
    symbol = await canonical_broker_symbol(broker, args["symbol"])
    provider = await broker_market(context.brokers, context.owner_id, args["account_id"])
    candles = await provider.candles(symbol, args["timeframe"], args["limit"])
    return {
        "symbol": symbol,
        "timeframe": args["timeframe"],
        "times": [c.time.isoformat() for c in candles],
        "indicator": args["name"],
        "series": indicator_series(args["name"], candles, args["period"]),
    }


def tools() -> list[Tool]:
    return [
        Tool(
            "chart_indicator",
            "Calculate a supported indicator from retrieved broker candles.",
            IndicatorInput,
            calculate,
            True,
        )
    ]
