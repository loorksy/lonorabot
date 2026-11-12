"""The Secret card's one submit (VISION.md 7.2, 10.3).

The owner's values go straight to the encrypted store and the card settles in the same
transaction. The card, its events, the conversation and the agent keep only the names.

A connecting card creates its connection in that transaction too: web search's Brave
key, a news feed or an economic calendar (its address, which may carry a key, is the
secret), or an MCP server (its address and optional token). An MCP server's tools are
read first, with the address and token the owner typed and no lock held; the same
transaction then saves the server, settles the card and raises the trust card that
follows (or wakes the agent), so a saved server never lacks its follow-up. A broker
card's values go only to the broker layer's store (7.2.3); the gateway then provisions
the account and wakes the agent with the result.
"""

from dataclasses import dataclass, field
from typing import Any, Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, Depends, Request
from lonora_adapters.storage.broker_secrets import BrokerSecrets
from lonora_adapters.storage.secret_store import EncryptedSecretStore
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.mcp import McpConnection
from lonora_contracts.owner_actions import SecretCardSave
from lonora_core.user_error import LonoraError
from lonora_db.integrations import feed_host, source_url
from lonora_db.owner_actions import (
    confirm_in_thread,
    continue_after_card,
    live_status,
    lock_owner_actions,
    owned_card,
    owner_action_data,
    raise_review_card,
    review_card_wanted,
    settle,
    supersede_subject,
)
from lonora_db.schema import IntegrationRow, OwnerActionRow
from lonora_db.secret_cards import card_values, free_names, save_values, secret_stale_reason
from lonora_db.secrets import BROKER, WORKSPACE
from lonora_security.network import endpoint_sha256
from lonora_tools.mcp import review_payload, tools_at
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..middleware.auth import require_owner, runtime
from ..runtime import ApiRuntime
from .integrations import OwnerIntegrationRepository
from .mcp import McpRepository

router = APIRouter(prefix="/owner-actions")


@dataclass(frozen=True)
class Offered:
    """What the MCP server the owner typed offers, read before the transaction: its
    tools (``read``), or none: ``unread`` (unreachable, a missing or wrong token, a
    timeout, an invalid list) or ``disabled`` (the operator's deny override: only
    declared tools run)."""

    state: Literal["read", "unread", "disabled"]
    address: str
    tools: list[dict[str, Any]] = field(default_factory=list[dict[str, Any]])


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
    offered = None
    if target == "mcp_server" and live_status(peek) == "pending":
        offered = await offered_tools(rt, card_values(peek, body.values))
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
        else:
            result = await connect(session, store, owner, row, card_values(row, body.values))
        if offered is not None:
            state, subject, review = await server_review(session, owner, result, offered)
            await settle_saved(session, owner, row, {**result, "review": state})
            if review is not None:
                # The server the owner just connected: its tools on the next card to
                # trust; the agent continues once the owner taps it.
                await raise_review_card(
                    session,
                    owner.id,
                    subject,
                    review,
                    agent_id=row.agent_id,
                    thread_id=row.thread_id,
                    run_id=row.run_id,
                )
            else:
                await continue_after_card(session, row)
        else:
            await settle_saved(session, owner, row, result)
            # The agent that asked continues the work that needed the secret. A broker
            # card's agent continues once the gateway has provisioned the account.
            if row.payload["destination"] != BROKER:
                await continue_after_card(session, row)
        return await owner_action_data(session, row)


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


async def offered_tools(rt: ApiRuntime, values: dict[str, str]) -> Offered:
    """The tools of the MCP server at the address the owner typed (network, no lock)."""
    address = https_address(values["URL"], "mcp_url_invalid")
    if not rt.settings.mcp_owner_trust:
        return Offered("disabled", address)
    try:
        return Offered("read", address, await tools_at(address, values.get("TOKEN")))
    except (LonoraError, UnicodeError):
        return Offered("unread", address)


async def server_review(
    session: AsyncSession, owner: OwnerIdentity, result: dict[str, Any], offered: Offered
) -> tuple[str, str, dict[str, Any] | None]:
    """What follows the saved server: ``raised`` (its trust card's subject and payload),
    ``already`` (a card for these tools waits or they are trusted), ``nothing_to_trust``
    (every tool can move money or is unsupported), ``unread`` or ``disabled``."""
    if offered.state != "read":
        return offered.state, "", None
    subject, review = review_payload(result["connection_id"], offered.address, offered.tools)
    if not review["tools"]:
        return "nothing_to_trust", "", None
    if await review_card_wanted(session, owner.id, review):
        return "raised", subject, review
    return "already", "", None


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
                transport="http",
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
