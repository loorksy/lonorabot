"""The Secret card's one submit (VISION.md 7.2, 10.3).

The owner's values go straight to the encrypted store and the card settles in the same
transaction. The card, its events, the conversation and the agent keep only the names.

A connecting card creates its connection in that transaction too: web search's Brave
key, a news feed or an economic calendar (its address, which may carry a key, is the
secret), or an MCP server (its address and optional token). A saved MCP server's tools
run once the owner trusts it, by naming it in chat (``mcp_trust``) or in Capabilities;
the agent that asked is woken to tell him. A broker card's values go only to the broker
layer's store (7.2.3); the gateway then provisions the account and wakes the agent with
the result. A model provider's key is checked with the provider first, with no lock held:
whether it accepts the key, never what it lists, since the provider's models are Lonora's
list (VISION 12.4). An OpenAI-compatible endpoint's base URL is checked, and its models
are read with the key, as they are the owner's. The same transaction then saves the key
and its record for the router (and the endpoint's catalog), settles the card and wakes
the agent to name the models that became available.
"""

import asyncio
import logging
from typing import Any
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request
from lonora_adapter_kit.model_errors import ModelProviderError
from lonora_adapters.storage.broker_secrets import BrokerSecrets
from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.mcp import McpConnection
from lonora_contracts.model_catalog import ModelDescriptor
from lonora_contracts.model_routing import PROVIDER_KEY_NAMES
from lonora_contracts.owner_actions import SecretCardSave
from lonora_core.user_error import LonoraError
from lonora_db.integrations import feed_host, source_url
from lonora_db.model_credentials import CONNECTION_SETTING
from lonora_db.owner_actions import (
    confirm_in_thread,
    continue_after_card,
    live_status,
    lock_owner_actions,
    owned_card,
    owner_action_data,
    settle,
    supersede_subject,
)
from lonora_db.schema import IntegrationRow, OwnerActionRow
from lonora_db.secret_cards import card_values, free_names, save_values, secret_stale_reason
from lonora_db.secrets import BROKER, WORKSPACE
from lonora_db.transactions import SettingsRepository
from lonora_providers.key_check import REJECTED, check_key
from lonora_providers.registry import OWNER_ENDPOINT, SIGN_IN, model_adapter
from lonora_security.network import compatible_endpoint, endpoint_sha256
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..middleware.auth import require_owner, runtime
from .integrations import OwnerIntegrationRepository
from .mcp import McpRepository
from .model_router import answer_unconfigured

router = APIRouter(prefix="/owner-actions")
log = logging.getLogger("lonora.secret_cards")
# One bounded check (the endpoint's catalog read) with the key the owner typed: the card
# never waits longer.
CATALOG_SECONDS = 20


@router.post("/{card_id}/secret")
async def save_secret(
    request: Request,
    card_id: str,
    body: SecretCardSave,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    rt = runtime(request)
    key = rt.settings.encryption_key.get_secret_value()
    store = EncryptedSecretStore(rt.db, key, owner.id)
    broker = BrokerSecrets(rt.db, key, owner.id)

    async def write(session: AsyncSession, name: str, value: str, scope: str) -> str:
        # A broker card's values go only to the broker layer (7.2.3).
        if scope == BROKER:
            return await broker.write_in_session(session, name, value)
        return await store.write_in_session(session, name, value, scope)

    async with rt.db.sessions() as session:
        peek = await owned_card(session, owner.id, card_id)
    target = peek.payload.get("connect") if peek.kind == "secret" else None
    if target == "model_provider" and peek.payload["details"]["provider"] in SIGN_IN:
        # This card signs in with ChatGPT (``chatgpt_sign_in``); it takes no value.
        raise LonoraError("chatgpt_sign_in_required", 409)
    catalog: list[ModelDescriptor] | None = None
    checked = "unchecked"
    if target == "model_provider" and live_status(peek) == "pending":
        if peek.payload["details"]["provider"] in OWNER_ENDPOINT:
            catalog = await offered_models(peek, card_values(peek, body.values))
        else:
            checked = await checked_key(peek, card_values(peek, body.values))
    async with rt.db.sessions() as session, session.begin():
        row = await pending_card(session, owner, card_id)
        if row is None:
            return await owner_action_data(session, await owned_card(session, owner.id, card_id))
        reason = await secret_stale_reason(session, owner.id, row.payload)
        if reason is not None:
            # Since the card was raised, web search got its key or a connection now uses
            # one of its names: like a stale decision, it settles with the reason and
            # saves nothing.
            await settle(session, row, "expired", reason)
            return await owner_action_data(session, row)
        if target is None:
            result = await save_values(session, row, body.values, write)
        elif target == "model_provider":
            provider = row.payload["details"]["provider"]
            result = await save_model_key(session, store, row, card_values(row, body.values))
            if provider in OWNER_ENDPOINT:
                result["catalog"] = None if catalog is None else len(catalog)
                # This key's catalog, empty when it could not be read: never the catalog
                # of the key it replaced.
                await SettingsRepository().put(
                    session,
                    "catalog:" + provider,
                    {"models": [item.model_dump(mode="json") for item in catalog or []]},
                )
            else:
                result["key"] = checked
        else:
            result = await connect(session, store, owner, row, card_values(row, body.values))
        await settle_saved(session, owner, row, result)
        # The agent that asked continues the work that needed the secret. A broker card's
        # agent continues once the gateway has provisioned the account.
        if row.payload["destination"] != BROKER:
            await continue_after_card(session, row)
        data = await owner_action_data(session, row)
    if target == "model_provider" and checked != "rejected":
        # With a model now, the replies that failed for lack of one run again. A key the
        # provider rejected gives no model: nothing is chosen from it, nothing re-run.
        await answer_unconfigured(request, owner)
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
    session: AsyncSession, owner: OwnerIdentity, row: OwnerActionRow, result: dict[str, Any]
) -> None:
    """Confirmed with its result, other cards for the same record superseded, and the
    confirmation line in the conversation."""
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
    await confirm_in_thread(session, row)


def https_address(address: str, code: str) -> str:
    """An https address with a host whose labels can be looked up, on port 443, without
    a user name, a password or a fragment; ``code`` refuses anything else."""
    try:
        endpoint_sha256(address)
        host = urlsplit(address).hostname or ""
        host.encode("idna")
    except (LonoraError, UnicodeError, ValueError):
        raise LonoraError(code, 422) from None
    return address


async def offered_models(
    card: OwnerActionRow, values: dict[str, str]
) -> list[ModelDescriptor] | None:
    """The catalog the provider lists for the key (and endpoint) the owner typed, read
    before the transaction with no lock held; None when it cannot be read (a rejected
    key, an unreachable, slow or unreadable endpoint). An unsafe endpoint URL is refused
    before any request, and the card stays waiting."""
    provider = card.payload["details"]["provider"]
    url = compatible_endpoint(values["URL"]) if "URL" in values else None
    adapter = model_adapter(provider, values["API_KEY"], url)
    try:
        async with asyncio.timeout(CATALOG_SECONDS):
            return await adapter.discover()
    except Exception as error:
        log.warning("model_catalog_unread provider=%s error=%s", provider, type(error).__name__)
        return None
    finally:
        await adapter.close()


async def checked_key(card: OwnerActionRow, values: dict[str, str]) -> str:
    """Whether the provider accepts the key the owner typed, asked before the transaction
    with no lock held: ``accepted``, ``rejected`` (a 401 or 403), or ``unchecked`` (no
    answer, or another one). The key is saved in every case; the agent says which."""
    provider = card.payload["details"]["provider"]
    adapter = model_adapter(provider, values["API_KEY"])
    try:
        async with asyncio.timeout(CATALOG_SECONDS):
            await check_key(adapter)
        return "accepted"
    except Exception as error:
        if isinstance(error, ModelProviderError) and error.http_status in REJECTED:
            return "rejected"
        log.warning("model_key_unchecked provider=%s error=%s", provider, type(error).__name__)
        return "unchecked"
    finally:
        await adapter.close()


async def save_model_key(
    session: AsyncSession,
    store: EncryptedSecretStore,
    row: OwnerActionRow,
    values: dict[str, str],
) -> dict[str, Any]:
    """The key as the owner's workspace secret under the provider's usual name, and the
    record the router reads it by: that secret's id with the endpoint URL it belongs to."""
    provider = row.payload["details"]["provider"]
    name = PROVIDER_KEY_NAMES[provider]
    url = compatible_endpoint(values["URL"]) if "URL" in values else None
    secret_id = await store.write_in_session(session, name, values["API_KEY"], WORKSPACE)
    await SettingsRepository().put(
        session, CONNECTION_SETTING + provider, {"secret_id": secret_id, "url": url}
    )
    return {"target": "model_provider", "provider": provider, "configured": True, "saved": [name]}


async def connect(
    session: AsyncSession,
    store: EncryptedSecretStore,
    owner: OwnerIdentity,
    row: OwnerActionRow,
    values: dict[str, str],
) -> dict[str, Any]:
    """Store the values as workspace secrets and create the connection that uses them."""
    target, details = row.payload["connect"], row.payload["details"]
    names = await free_names(session, owner.id, target, details["name"])
    if target == "mcp_server":
        address = https_address(values["URL"], "mcp_url_invalid")
        saved = [names["URL"]]
        address_id = await store.write_in_session(session, names["URL"], address, WORKSPACE)
        token_id = None
        if values.get("TOKEN"):
            token_id = await store.write_in_session(
                session, names["TOKEN"], values["TOKEN"], WORKSPACE
            )
            saved.append(names["TOKEN"])
        server = await McpRepository().create(
            session,
            owner.id,
            McpConnection(
                name=details["name"],
                url_secret_id=address_id,
                endpoint_sha256=endpoint_sha256(address),
                secret_id=token_id,
                enabled=True,
            ).model_dump(mode="json"),
        )
        return {"target": target, "connection_id": server.id, "configured": True, "saved": saved}
    payload: dict[str, Any] = {"type": target, "name": details["name"], "enabled": True}
    if target == "brave_search":
        key = values["API_KEY"]
    else:
        # A feed's or calendar's address: checked as its reader checks it, kept in the
        # store, its host on the row.
        key = values["URL"]
        if target == "news_feed":
            feed_host(key)
        else:
            https_address(key, "integration_source_invalid")
        host = urlsplit(key).hostname
        if not host:
            raise LonoraError("integration_source_invalid", 422)
        existing = await same_source(session, store, owner, target, key)
        if existing is not None:
            # This address is already connected: nothing new is saved or created.
            return {
                "target": target,
                "integration_id": existing.id,
                "configured": True,
                "saved": [],
            }
        payload["domain"] = host
    (name,) = names.values()
    payload["secret_id"] = await store.write_in_session(session, name, key, WORKSPACE)
    created = await OwnerIntegrationRepository().create(session, owner.id, payload)
    return {"target": target, "integration_id": created.id, "configured": True, "saved": [name]}


async def same_source(
    session: AsyncSession,
    store: EncryptedSecretStore,
    owner: OwnerIdentity,
    target: str,
    address: str,
) -> IntegrationRow | None:
    """An enabled feed or calendar of this kind already reading this address."""
    rows = await session.scalars(select(IntegrationRow).where(IntegrationRow.owner_id == owner.id))
    for row in rows:
        if row.payload.get("type") != target or not row.payload.get("enabled"):
            continue
        try:
            if await source_url(row.payload, store.read) == address:
                return row
        except LonoraError:
            continue
    return None
