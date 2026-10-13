from typing import Any

from lonora_contracts.domain import Contract
from lonora_market.broker import broker_market
from pydantic import Field

from .base import Tool
from .context import ToolContext


class AccountInput(Contract):
    account_id: str = Field(
        description="Internal connection_id returned by list_accounts; not the external broker account ID."
    )


class QuoteInput(AccountInput):
    symbol: str


class CandlesInput(QuoteInput):
    timeframe: str
    limit: int = Field(default=300, ge=1, le=1000)


async def instruments(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    provider = await broker_market(context.brokers, context.owner_id, args["account_id"])
    return {"instruments": [i.model_dump(mode="json") for i in await provider.instruments()]}


async def quote(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    provider = await broker_market(context.brokers, context.owner_id, args["account_id"])
    return (await provider.quote(args["symbol"])).model_dump(mode="json")


async def candles(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    provider = await broker_market(context.brokers, context.owner_id, args["account_id"])
    return {
        "candles": [
            c.model_dump(mode="json")
            for c in await provider.candles(args["symbol"], args["timeframe"], args["limit"])
        ]
    }


def tools() -> list[Tool]:
    return [
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
