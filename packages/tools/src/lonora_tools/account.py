from datetime import datetime
from typing import Any

from lonora_contracts.domain import Contract
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_trading.accounts import account_snapshot
from pydantic import Field, model_validator

from .base import Tool
from .context import ToolContext
from .market import AccountInput


class HistoryInput(AccountInput):
    start: datetime
    end: datetime
    limit: int = Field(default=100, ge=1, le=1000)

    @model_validator(mode="after")
    def check_range(self) -> "HistoryInput":
        if (
            self.start.tzinfo is None
            or self.end.tzinfo is None
            or self.end < self.start
            or (self.end - self.start).days > 90
        ):
            raise ValueError("invalid_history_range")
        return self


async def history(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = HistoryInput.model_validate(args)
    broker = await context.brokers.get(context.owner_id, params.account_id)
    return {
        "history": await broker.history(params.start, params.end, params.limit),
        "start": params.start.isoformat(),
        "end": params.end.isoformat(),
    }


class ListAccountsInput(Contract):
    pass


async def list_accounts(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    async with context.db.sessions() as session:
        rows = await BrokerSessionRepository().list(session, context.owner_id)
        return {
            "accounts": [
                {
                    "connection_id": row.id,
                    "broker_identity": row.state.get("broker_identity")
                    if row.state.get("broker_identity", {}).get("connection_version") == row.version
                    else None,
                    "provider": row.payload["provider"],
                    "enabled": row.payload["enabled"],
                    "credentials_configured": bool(row.payload.get("secret_id")),
                }
                for row in rows
            ],
            "guidance": "Use connection_id as account_id in account, market and trading tools. "
            "Present accounts to the user using broker_identity broker/login/server, never transport IDs as account numbers. "
            "Missing identity means it has not been observed. Verify using account_read, which refreshes native identity; a saved connection is not proof of live broker connectivity.",
        }


async def read(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    return await account_snapshot(
        await context.brokers.get(context.owner_id, args["account_id"]),
        await context.brokers.account(context.owner_id, args["account_id"]),
    )


def tools() -> list[Tool]:
    return [
        Tool(
            "account_history",
            "Read bounded broker deal history over an explicit timezone-aware time range of at most 90 days; use the internal connection ID.",
            HistoryInput,
            history,
            True,
        ),
        Tool(
            "list_accounts",
            "List the owner's saved broker connections with exact internal "
            "connection_id for tool routing and cached broker-native identity. No credentials or MetaApi transport account IDs are returned. "
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
