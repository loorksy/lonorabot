from typing import Any

from lonora_contracts.domain import Contract
from lonora_market.broker import broker_market
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
        description="Broker timeframe: 1m, 5m, 15m, 30m, 1h, 4h, 1d or 1w; not M15/H1."
    )
    limit: int = Field(default=300, ge=1, le=1000)


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
    ]
