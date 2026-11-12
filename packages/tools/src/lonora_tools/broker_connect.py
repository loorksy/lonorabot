"""Connect the owner's trading account from chat (VISION.md 9.2)."""

from typing import Any

from lonora_contracts.domain import Contract
from lonora_core.user_error import ToolRefusal
from lonora_db.broker_sessions import BrokerSessionRepository
from lonora_db.owner_actions import propose_effect
from lonora_db.runs import require_lease
from lonora_db.schema import SecretRow
from lonora_db.secret_cards import broker_card_payload
from lonora_db.secrets import BROKER, METAAPI_TOKEN
from lonora_session.idempotency import stable_id
from lonora_trading.broker_provisioning import platform_of
from pydantic import Field
from sqlalchemy import select

from .base import Tool
from .context import ToolContext
from .owner_actions import card_scope, card_summary
from .restrictions import owner_message_id


class BrokerConnectInput(Contract):
    login: str = Field(pattern=r"^\s*\d{1,20}\s*$")
    server: str = Field(min_length=2, max_length=80, pattern=r"^[\w .\-]+$")
    platform: str | None = Field(default=None, pattern=r"^mt[45]$")


async def connect(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = BrokerConnectInput.model_validate(args)
    login, server = params.login.strip(), params.server.strip()
    platform = params.platform or platform_of(server)
    if platform is None:
        raise ToolRefusal(
            "broker_platform_required",
            422,
            details={"hint": "Ask the owner whether the account is MT4 or MT5, then call again."},
        )
    async with context.db.sessions() as session, session.begin():
        run, thread = await card_scope(context, session)
        # A password card for a server the owner did not name would send their password
        # where a page or a peer chose (6.10): only the owner's own typed message asks.
        if await owner_message_id(session, run) is None:
            raise ToolRefusal(
                "broker_connect_needs_owner_message",
                403,
                details={"hint": "Connect an account only when the owner asks in chat."},
            )
        repository = BrokerSessionRepository()
        await repository.lock_owner(session, context.owner_id)
        await repository.assert_unique(
            session,
            context.owner_id,
            {"provider": "metaapi", "account_id": "provisioning:" + run.id},
            identity={"login": login, "server": server, "platform": platform},
        )
        token_saved = await session.scalar(
            select(SecretRow.id).where(
                SecretRow.owner_id == context.owner_id,
                SecretRow.scope == BROKER,
                SecretRow.name == METAAPI_TOKEN,
            )
        )
        subject, payload = broker_card_payload(
            login=login, server=server, platform=platform, token_needed=token_saved is None
        )
        row, created = await propose_effect(
            session,
            context.owner_id,
            "secret",
            subject,
            payload,
            card_id=stable_id(context.resource_id, "broker-connect"),
            agent_id=context.agent_id,
            thread_id=thread.id,
            run_id=run.id,
        )
        await require_lease(session, context.lease, lock=True)
        return {
            **card_summary(row, created, thread.id, False),
            "asks_for": [field["key"] for field in payload["fields"]],
            "next": "The server provisions and deploys the account after the owner saves; "
            "you are woken with its balance or the reason it failed. Do not ask for the "
            "password in chat.",
        }


def tools() -> list[Tool]:
    return [
        Tool(
            "broker_connect",
            "Connect the owner's MetaTrader account through MetaApi. Ask in chat for the "
            "account number (login) and the broker server name, then call with them; "
            "platform mt4/mt5 only when the server name does not say. The server shows a "
            "card for the trading password (and the MetaApi API token the first time), "
            "provisions and deploys the account, and wakes you with its balance. Only on "
            "the owner's own request.",
            BrokerConnectInput,
            connect,
            search_terms="link add broker trading account metatrader exness login password "
            "ربط حساب تداول وسيط ميتاتريدر",
        ),
    ]
