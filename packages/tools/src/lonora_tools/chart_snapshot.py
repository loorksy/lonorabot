from typing import Any

from lonora_charts.snapshot import svg_snapshot
from lonora_market.broker import broker_market

from .artifacts import store_artifact
from .base import Tool
from .context import ToolContext
from .market import CandlesInput


async def snapshot(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    provider = await broker_market(context.brokers, context.owner_id, args["account_id"])
    candles = await provider.candles(args["symbol"], args["timeframe"], args["limit"])
    image = svg_snapshot(args["symbol"], candles)
    return await store_artifact(context, args["symbol"] + ".svg", image.encode(), "image/svg+xml")


def tools() -> list[Tool]:
    return [
        Tool(
            "chart_snapshot",
            "Save a chart snapshot artifact from real candle data.",
            CandlesInput,
            snapshot,
        )
    ]
