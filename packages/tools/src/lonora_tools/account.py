from typing import Any

from lonora_contracts.domain import Contract
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_trading.accounts import account_snapshot

from .base import Tool
from .context import ToolContext
from .market import AccountInput


class ListAccountsInput(Contract):
    pass


async def list_accounts(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        rows = await BrokerSessionRepository().list(session, context.owner_id)
        return {
            "accounts": [
                {
                    "connection_id": row.id,
                    "broker_account_id": row.payload["account_id"],
                    "provider": row.payload["provider"],
                    "enabled": row.payload["enabled"],
                    "credentials_configured": bool(row.payload.get("secret_id")),
                }
                for row in rows
            ],
            "guidance": "Use connection_id as account_id in account, market and trading tools. "
            "A saved connection is not proof of live broker connectivity; verify using account_read.",
        }


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return await account_snapshot(await context.brokers.get(context.owner_id, args["account_id"]))


def tools() -> list[Tool]:
    return [
        Tool(
            "list_accounts",
            "List the owner's saved broker connections with exact internal "
            "connection_id and external broker_account_id. No credentials are returned. "
            "Discover these before account_read; do not guess IDs.",
            ListAccountsInput,
            list_accounts,
            True,
        ),
        Tool(
            "account_read",
            "Read real balance/equity/margin, positions and orders. account_id must be the internal connection_id returned by list_accounts, not the external MetaApi account ID.",
            AccountInput,
            read,
            True,
        ),
    ]
