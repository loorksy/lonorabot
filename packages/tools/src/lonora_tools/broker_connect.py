"""Connect the owner's trading account from chat (VISION.md 9.2)."""

from typing import Any, Literal

from lonora_contracts.domain import Contract
from lonora_core.user_error import ToolRefusal
from lonora_db.broker_sessions import BrokerSessionRepository, current_broker_identity
from lonora_db.owner_actions import propose_effect
from lonora_db.runs import require_lease
from lonora_db.schema import SecretRow
from lonora_db.secret_cards import broker_card_payload
from lonora_db.secrets import BROKER, METAAPI_TOKEN
from lonora_session.idempotency import stable_id
from lonora_trading.broker_provisioning import (
    lock_provisioning,
    other_card_active,
    platform_of,
)
from pydantic import Field
from sqlalchemy import select

from .base import Tool
from .context import ToolContext
from .owner_actions import card_scope, card_summary
from .provenance import owner_message_id


class BrokerConnectInput(Contract):
    login: str = Field(pattern=r"^\s*\d{1,20}\s*$")
    server: str = Field(min_length=2, max_length=80, pattern=r"^[\w .\-]+$")
    platform: str | None = Field(default=None, pattern=r"^[mM][tT][45]$")


async def connect(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = BrokerConnectInput.model_validate(args)
    login, server = params.login.strip(), params.server.strip()
    # The server's own name wins when it says MT4 or MT5.
    platform = platform_of(server) or (params.platform or "").lower() or None
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
        # The provisioning lock (advisory, no row), as the gateway's step takes it.
        await lock_provisioning(session, context.owner_id)
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
        if await other_card_active(session, context.owner_id, subject, ""):
            raise ToolRefusal(
                "broker_connect_in_progress",
                409,
                details={"hint": "That account is being connected; you are woken when done."},
            )
        await repository.assert_unique(
            session,
            context.owner_id,
            {"provider": "metaapi", "account_id": "provisioning:" + run.id},
            identity={"login": login, "server": server, "platform": platform},
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
        *manage_tools(),
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


class BrokerManageInput(Contract):
    account_id: str = Field(min_length=1, max_length=64)
    action: Literal["disconnect", "enable", "disable", "rotate_password", "replace_token"]


async def manage(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    """9.3 from chat. Every action is the owner's own: the run must carry their typed
    message (Q10), so a page or a peer cannot disconnect, switch off or re-key an account."""
    from lonora_trading.broker_manage import disconnect, refuse_unsettled, set_enabled

    params = BrokerManageInput.model_validate(args)
    async with context.db.sessions() as session:
        run = await require_lease(session, context.lease)
        if await owner_message_id(session, run) is None:
            raise ToolRefusal(
                "broker_manage_needs_owner_message",
                403,
                details={"hint": "Change a broker connection only when the owner asks in chat."},
            )
        row = await BrokerSessionRepository().get(session, context.owner_id, params.account_id)
        identity = current_broker_identity(row) or {}
    if params.action in {"enable", "disable"}:
        return await set_enabled(
            context.db,
            context.brokers,
            context.owner_id,
            params.account_id,
            params.action == "enable",
        )
    if params.action == "disconnect":
        return await disconnect(context.db, context.brokers, context.owner_id, params.account_id)
    if params.action == "rotate_password":
        await refuse_unsettled(context.db, context.owner_id, params.account_id)
    if not identity.get("login") or row.payload.get("provider") != "metaapi":
        raise ToolRefusal("broker_not_metaapi", 409)
    # A new password or token: a broker card fixed by the server, like connecting.
    async with context.db.sessions() as session, session.begin():
        run, thread = await card_scope(context, session)
        subject, payload = broker_card_payload(
            login=str(identity["login"]),
            server=str(identity.get("server") or ""),
            platform=str(identity.get("platform") or "mt5"),
            token_needed=False,
            purpose=params.action,
            connection_id=params.account_id,
        )
        card, created = await propose_effect(
            session,
            context.owner_id,
            "secret",
            subject,
            payload,
            card_id=stable_id(context.resource_id, "broker-manage"),
            agent_id=context.agent_id,
            thread_id=thread.id,
            run_id=run.id,
        )
        await require_lease(session, context.lease, lock=True)
        return {
            **card_summary(card, created, thread.id, False),
            "asks_for": [field["key"] for field in payload["fields"]],
        }


def manage_tools() -> list[Tool]:
    return [
        Tool(
            "broker_manage",
            "Change one of the owner's broker connections on the owner's own request: "
            "disconnect (an account Lonora created at MetaApi is removed there too; its open "
            "positions and orders stay at the broker, unmanaged), enable, "
            "disable (its positions are then not read or managed), rotate_password or "
            "replace_token (each shows a card for the new value; you never see it). "
            "account_id is the connection_id from list_accounts. Refused while an operation "
            "on the account has no confirmed outcome.",
            BrokerManageInput,
            manage,
            search_terms="disconnect unlink remove disable enable password token broker "
            "فصل حذف تعطيل تفعيل كلمة مرور رمز وسيط",
        ),
    ]
