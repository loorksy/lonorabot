from typing import Any

from lonora_trading.accounts import account_snapshot

from .base import Tool
from .context import ToolContext
from .market import AccountInput


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return await account_snapshot(await context.brokers.get(context.owner_id, args["account_id"]))


def tools() -> list[Tool]:
    return [
        Tool(
            "account_read",
            "Read account balance/equity/margin, exact positions and orders through the broker-neutral interface.",
            AccountInput,
            read,
            True,
        )
    ]
