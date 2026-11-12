"""The Secret card's one submit (VISION.md 7.2, 10.3).

The owner's values go straight to the encrypted store and the card settles in the same
transaction. The card, its events, the conversation and the agent keep only the names.

A connecting card creates its connection in that transaction too: web search's Brave
key, a news feed or an economic calendar (its address, which may carry a key, is the
secret), or an MCP server (its token; its tools are then read, outside the transaction,
for the trust card that follows). A broker's MetaApi token is verified with MetaApi
first; the card settles inside the transaction that stores the token and creates the
connection. A model provider's key (and an OpenAI-compatible endpoint's base URL) is
saved in the transaction; its catalog is then read, outside it, before the agent that
asked is woken to name the models that became available.
"""

import asyncio
import logging
from dataclasses import dataclass
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request
from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.broker import BrokerConnection
from lonora_contracts.mcp import McpConnection
from lonora_contracts.model_routing import PROVIDER_KEY_NAMES
from lonora_contracts.owner_actions import SecretCardSave
from lonora_core.user_error import LonoraError
from lonora_db.integrations import feed_host
from lonora_db.model_credentials import CONNECTION_SETTING
from lonora_db.owner_actions import (
    confirm_in_thread,
    continue_after_card,
    live_status,
    lock_owner_actions,
    owned_card,
    owner_action_data,
    owner_action_event,
    raise_review_card,
    review_card_wanted,
    settle,
    supersede_subject,
)
from lonora_db.schema import McpConnectionRow, OwnerActionRow
from lonora_db.secret_cards import card_values, free_name, save_values
from lonora_db.secrets import WORKSPACE
from lonora_db.transactions import SettingsRepository
from lonora_providers.credentials import ProviderCredentials
from lonora_providers.discovery import discover_models
from lonora_tools.mcp import advertised_tools, review_payload
from lonora_trading.connections import connect_account
from sqlalchemy.ext.asyncio import AsyncSession

from ..middleware.auth import require_owner, runtime
from ..runtime import ApiRuntime
from .integrations import OwnerIntegrationRepository
from .mcp import McpRepository
from .model_router import answer_unconfigured

router = APIRouter(prefix="/owner-actions")
log = logging.getLogger("lonora.secret_cards")


@dataclass(frozen=True)
class ServerReview:
    """What a newly connected MCP server offers to trust: ``review`` (a trust card
    follows), ``unread`` (its tools could not be read now), ``nothing_to_trust`` (every
    tool can move money or is unsupported) or ``disabled`` (the operator's deny override:
    only declared tools run)."""

    state: Literal["review", "unread", "nothing_to_trust", "disabled"]
    subject: str = ""
    payload: dict[str, Any] | None = None


@router.post("/{card_id}/secret")
async def save_secret(
    request: Request,
    card_id: str,
    body: SecretCardSave,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    rt = runtime(request)
    store = EncryptedSecretStore(rt.db, rt.settings.encryption_key.get_secret_value(), owner.id)
    async with rt.db.sessions() as session:
        peek = await owned_card(session, owner.id, card_id)
        target = peek.payload.get("connect") if peek.kind == "secret" else None
    if target == "broker":
        return await save_broker(rt, store, owner, card_id, body.values)
    async with rt.db.sessions() as session, session.begin():
        row = await pending_card(session, owner, card_id)
        if row is None:
            return await owner_action_data(session, await owned_card(session, owner.id, card_id))
        if target is None:
            result = await save_values(session, row, body.values, store.write_in_session)
        else:
            values = card_values(row, body.values)
            result = await connect(session, store, owner, row, values)
        later = target in {"mcp_server", "model_provider"}
        await settle_saved(session, owner, row, result, follow=not later)
        data = await owner_action_data(session, row)
    if target == "mcp_server":
        data = await follow_mcp(rt, owner, card_id, row.result["connection_id"])
    elif target == "model_provider":
        data = await follow_model(request, owner, card_id, row.payload["details"]["provider"])
    return data


async def pending_card(
    session: AsyncSession, owner: OwnerIdentity, card_id: str
) -> OwnerActionRow | None:
    """The Secret card, locked, while it waits; None once it is settled (a second tap
    shows it as it is and writes nothing)."""
    await lock_owner_actions(session, owner.id)
    row = await owned_card(session, owner.id, card_id, lock=True)
    if row.kind != "secret":
        raise LonoraError("owner_action_not_secret", 409)
    status = live_status(row)
    if status == "expired" and row.status == "pending":
        await settle(session, row, "expired", "expired")
    return row if status == "pending" else None


async def settle_saved(
    session: AsyncSession,
    owner: OwnerIdentity,
    row: OwnerActionRow,
    result: dict[str, Any],
    *,
    follow: bool,
) -> None:
    await settle(session, row, "confirmed", None, via="tap", result=result)
    await supersede_subject(
        session,
        owner.id,
        row.kind,
        row.subject,
        "done_by_another_card",
        keep=row.id,
        effect=row.payload_hash,
    )
    if follow:
        await confirm_in_thread(session, row)
        # The agent that asked continues the work that needed the secret.
        await continue_after_card(session, row)


async def connect(
    session: AsyncSession,
    store: EncryptedSecretStore,
    owner: OwnerIdentity,
    row: OwnerActionRow,
    values: dict[str, str],
) -> dict[str, Any]:
    """Store the value as a workspace secret and create the connection that uses it."""
    target, details = row.payload["connect"], row.payload["details"]
    if target == "model_provider":
        provider = details["provider"]
        name = PROVIDER_KEY_NAMES[provider]
        secret_id = await store.write_in_session(session, name, values["API_KEY"], WORKSPACE)
        # The router's key is this secret, by id, with the URL it belongs to.
        await SettingsRepository().put(
            session,
            CONNECTION_SETTING + provider,
            {"secret_id": secret_id, "url": details.get("url")},
        )
        return {"target": target, "provider": provider, "configured": True, "saved": [name]}
    if target == "mcp_server":
        saved: list[str] = []
        secret_id = None
        if values.get("TOKEN"):
            name = await free_name(session, owner.id, target, details["name"])
            secret_id = await store.write_in_session(session, name, values["TOKEN"], WORKSPACE)
            saved.append(name)
        server = await McpRepository().create(
            session,
            owner.id,
            McpConnection(
                name=details["name"],
                url=details["url"],
                transport="http",
                secret_id=secret_id,
                enabled=True,
            ).model_dump(mode="json"),
        )
        return {"target": target, "connection_id": server.id, "configured": True, "saved": saved}
    payload: dict[str, Any] = {"type": target, "name": details["name"], "enabled": True}
    if target == "brave_search":
        key = values["API_KEY"]
    else:
        # A feed's or calendar's address: checked here, kept in the store, its host here.
        key = values["URL"].strip()
        if target == "news_feed":
            feed_host(key)
        host = urlsplit(key).hostname
        if not host or urlsplit(key).scheme not in {"https", "http"}:
            raise LonoraError("integration_source_invalid", 422)
        payload["domain"] = host
    name = await free_name(session, owner.id, target, details["name"])
    payload["secret_id"] = await store.write_in_session(session, name, key, WORKSPACE)
    created = await OwnerIntegrationRepository().create(session, owner.id, payload)
    return {"target": target, "integration_id": created.id, "configured": True, "saved": [name]}


async def save_broker(
    rt: ApiRuntime,
    store: EncryptedSecretStore,
    owner: OwnerIdentity,
    card_id: str,
    values: dict[str, str],
) -> dict[str, Any]:
    """A broker card: the token is checked with MetaApi first (no lock held), then the
    card settles in the transaction that stores the token (broker scope) and creates the
    connection; a card decided meanwhile creates nothing."""
    async with rt.db.sessions() as session:
        row = await owned_card(session, owner.id, card_id)
        if live_status(row) != "pending":
            return await owner_action_data(session, row)
        token = card_values(row, values)["METAAPI_TOKEN"]
        config = BrokerConnection(
            provider="metaapi",
            account_id=row.payload["details"]["metaapi_account_id"],
            region=None,
            enabled=True,
        )

    async def settle_card(session: AsyncSession) -> None:
        current = await pending_card(session, owner, card_id)
        if current is None:
            raise LonoraError("owner_action_expired_or_decided", 409)
        result: dict[str, Any] = {"target": "broker", "configured": True, "saved": []}
        await settle_saved(session, owner, current, result, follow=True)

    await connect_account(rt.db, store, owner.id, config, token, within=settle_card)
    async with rt.db.sessions() as session:
        return await owner_action_data(session, await owned_card(session, owner.id, card_id))


async def follow_mcp(
    rt: ApiRuntime, owner: OwnerIdentity, card_id: str, connection_id: str
) -> dict[str, Any]:
    """After the server is saved: read its tools (network, no lock held), then the
    confirmation line and the trust card that follows, or the agent's next run when no
    card can follow."""
    review = await server_review(rt, owner, connection_id)
    async with rt.db.sessions() as session, session.begin():
        await lock_owner_actions(session, owner.id)
        row = await owned_card(session, owner.id, card_id, lock=True)
        state = review.state
        if state == "review" and review.payload is not None:
            state = (
                "raised"
                if await review_card_wanted(session, owner.id, review.payload)
                else "already"
            )
        row.result = {**row.result, "review": state}
        await owner_action_event(session, row)
        await confirm_in_thread(session, row)
        if state == "raised" and review.payload is not None:
            # The server the owner just connected: its tools on the next card to trust;
            # the agent continues once the owner taps it.
            await raise_review_card(
                session,
                owner.id,
                review.subject,
                review.payload,
                agent_id=row.agent_id,
                thread_id=row.thread_id,
                run_id=row.run_id,
            )
        else:
            await continue_after_card(session, row)
        return await owner_action_data(session, row)


# One bounded catalog read after a provider key is saved: the card never waits longer.
CATALOG_SECONDS = 20


async def follow_model(
    request: Request, owner: OwnerIdentity, card_id: str, provider: str
) -> dict[str, Any]:
    """After the key is saved: read the provider's catalog (network, no lock held), let
    the replies that failed for lack of a model run again, then the confirmation line
    and the asking agent's next run, which names the models that became available."""
    rt = runtime(request)
    credentials = ProviderCredentials(rt.db, rt.services(owner.id).secrets)
    catalog: int | None = None
    try:
        async with asyncio.timeout(CATALOG_SECONDS):
            catalog = len(await discover_models(rt.db, credentials, provider))
    except Exception as error:
        # A rejected key, an unreachable or slow endpoint, or a listing the adapter cannot
        # read (an owner's endpoint answers what it likes): the card is already saved, so
        # the agent is still woken, and says so.
        log.warning("model_catalog_unread provider=%s error=%s", provider, type(error).__name__)
        catalog = None
    await answer_unconfigured(request, owner)
    async with rt.db.sessions() as session, session.begin():
        await lock_owner_actions(session, owner.id)
        row = await owned_card(session, owner.id, card_id, lock=True)
        row.result = {**row.result, "catalog": catalog}
        await owner_action_event(session, row)
        await confirm_in_thread(session, row)
        await continue_after_card(session, row)
        return await owner_action_data(session, row)


async def server_review(rt: ApiRuntime, owner: OwnerIdentity, connection_id: str) -> ServerReview:
    if not rt.settings.mcp_owner_trust:
        return ServerReview("disabled")
    async with rt.db.sessions() as session:
        server = await session.get(McpConnectionRow, connection_id)
        if server is None or server.owner_id != owner.id:
            return ServerReview("unread")
        config = McpConnection.model_validate(server.payload)
    if not config.enabled or config.transport != "http" or not config.url:
        return ServerReview("unread")
    try:
        tools = await advertised_tools(rt.services(owner.id).secrets, config)
        subject, payload = review_payload(connection_id, config.url, tools)
    except LonoraError:
        # Unreachable, a missing or wrong token, a timeout or an invalid list.
        return ServerReview("unread")
    if not payload["tools"]:
        return ServerReview("nothing_to_trust")
    return ServerReview("review", subject, payload)
