from decimal import Decimal
from typing import Any

from lonora_contracts.domain import Contract, utcnow
from lonora_core.chart_controller import validate_timeframe
from lonora_market.broker import broker_market
from lonora_market.structure import analyze_structure
from pydantic import Field

from .base import Tool
from .context import ToolContext
from .symbols import canonical_broker_symbol


class AccountInput(Contract):
    account_id: str = Field(
        description="Internal connection_id returned by list_accounts; not the external broker account ID."
    )


class QuoteInput(AccountInput):
    symbol: str


class CandlesInput(QuoteInput):
    timeframe: str = Field(
        description="Exact supported broker timeframe, e.g. 15m, 1h or 1mn; not M15/H1."
    )
    limit: int = Field(default=300, ge=1, le=1000)


class StructureInput(CandlesInput):
    left_bars: int = Field(default=2, ge=1, le=100)
    right_bars: int = Field(default=2, ge=1, le=100)
    tolerance: Decimal = Field(default=Decimal(0), ge=0)
    max_pivots: int = Field(default=24, ge=1, le=100)
    max_lines: int = Field(default=6, ge=1, le=24)


async def symbols(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    broker = await context.brokers.get(context.owner_id, args["account_id"])
    return {"symbols": await broker.symbols()}


async def instrument(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    broker = await context.brokers.get(context.owner_id, args["account_id"])
    symbol = await canonical_broker_symbol(broker, args["symbol"])
    return (await broker.instrument(symbol)).model_dump(mode="json")


async def instruments(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    provider = await broker_market(context.brokers, context.owner_id, args["account_id"])
    return {"instruments": [i.model_dump(mode="json") for i in await provider.instruments()]}


async def quote(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    broker = await context.brokers.get(context.owner_id, args["account_id"])
    symbol = await canonical_broker_symbol(broker, args["symbol"])
    provider = await broker_market(context.brokers, context.owner_id, args["account_id"])
    return (await provider.quote(symbol)).model_dump(mode="json")


async def candles(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    broker = await context.brokers.get(context.owner_id, args["account_id"])
    symbol = await canonical_broker_symbol(broker, args["symbol"])
    provider = await broker_market(context.brokers, context.owner_id, args["account_id"])
    return {
        "candles": [
            c.model_dump(mode="json")
            for c in await provider.candles(symbol, args["timeframe"], args["limit"])
        ]
    }


async def structure(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    timeframe = validate_timeframe(args["timeframe"])
    broker = await context.brokers.get(context.owner_id, args["account_id"])
    symbol = await canonical_broker_symbol(broker, args["symbol"], require_exists=True)
    provider = await broker_market(context.brokers, context.owner_id, args["account_id"])
    series = await provider.candles(symbol, timeframe, args["limit"])
    return analyze_structure(
        series,
        account_id=args["account_id"],
        symbol=symbol,
        timeframe=timeframe,
        observed_at=utcnow(),
        left_bars=args["left_bars"],
        right_bars=args["right_bars"],
        tolerance=Decimal(str(args["tolerance"])),
        max_pivots=args["max_pivots"],
        max_lines=args["max_lines"],
    )


def tools() -> list[Tool]:
    return [
        Tool(
            "market_symbols",
            "Discover exact broker symbol names without loading specifications for every instrument. "
            "Use before guessing broker symbols or aliases; suffixes matter. When an immutable trading market "
            "is bound, omit account_id and do not ask the owner to repeat the symbol.",
            AccountInput,
            symbols,
            True,
        ),
        Tool(
            "market_instrument",
            "Read specifications for ONE exact broker symbol from market_symbols. Prefer this to loading every instrument for a single-symbol analysis.",
            QuoteInput,
            instrument,
            True,
        ),
        Tool(
            "market_instruments",
            "Discover exact broker symbols and contract specifications.",
            AccountInput,
            instruments,
            True,
        ),
        Tool(
            "market_quote",
            "Read a sourced quote and observation time for an exact broker symbol.",
            QuoteInput,
            quote,
            True,
        ),
        Tool(
            "market_candles",
            "Read historical broker candles without symbol rewriting.",
            CandlesInput,
            candles,
            True,
        ),
        Tool(
            "market_structure",
            "Measure confirmed swings and alternative support/resistance trendlines from closed broker bars. "
            "Explicit left/right windows reject tied extrema; confirmation is delayed until right bars close. "
            "Tolerance is an absolute price distance. Returns exact anchors, source evidence and line breaks "
            "for existing chart drawings; no trade signal or execution authority.",
            StructureInput,
            structure,
            True,
        ),
    ]
