"""The Secret card (VISION.md 7.2, 10.3): how a credential reaches Lonora.

The agent chooses the card's label and fields (each a key, the name agents use, and a
label the owner reads); the server sets where the values go. The owner's values go
straight to the encrypted store in the same transaction that settles the card; the card,
its events and the conversation keep only the keys. The agent learns "saved".
"""

from collections.abc import Awaitable, Callable
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import OwnerActionRow, SecretRow
from .secrets import BROKER, METAAPI_TOKEN, WORKSPACE, metaapi_password_name

# Writes one value to the encrypted store in the caller's transaction; returns its id.
SecretWriter = Callable[[AsyncSession, str, str, str], Awaitable[str]]


def secret_card_payload(proposal: OwnerActionProposal) -> tuple[str, dict[str, Any]]:
    """A card the agent raised: its own label and fields, for the workspace."""
    assert proposal.label is not None and proposal.secret_fields is not None
    fields = [field.model_dump(mode="json") for field in proposal.secret_fields]
    keys = sorted(field["key"] for field in fields)
    return "secret:" + WORKSPACE + ":" + ",".join(keys), {
        "label": proposal.label,
        "fields": fields,
        "destination": WORKSPACE,
    }


# A broker-destination card (7.2.3) is raised only by the connect tool, which fixes its
# fields: the trading password, and the MetaApi API token while none is saved.
PASSWORD_FIELD = "PASSWORD"
TOKEN_FIELD = "METAAPI_TOKEN"


def broker_card_payload(
    *, login: str, server: str, platform: str, token_needed: bool
) -> tuple[str, dict[str, Any]]:
    """The connect card for one trading account. The login and server are shown as
    server facts, so the owner sees which account the password is for."""
    fields = [{"key": PASSWORD_FIELD, "label": "Trading password", "secret": True}]
    if token_needed:
        fields.append({"key": TOKEN_FIELD, "label": "MetaApi API token", "secret": True})
    return "secret:broker:" + server.casefold() + ":" + login, {
        "label": login + " @ " + server,
        "fields": fields,
        "destination": BROKER,
        "account": {"login": login, "server": server, "platform": platform},
    }


def secret_facts(payload: dict[str, Any], agent_name: str | None) -> dict[str, Any]:
    """What the card shows: its label and fields, where the values go, and who asked."""
    facts = {
        "label": payload["label"],
        "fields": payload["fields"],
        "destination": payload["destination"],
        "agent_name": agent_name,
    }
    if payload["destination"] == BROKER:
        facts["account"] = payload["account"]
    return facts


async def save_values(
    session: AsyncSession, row: OwnerActionRow, values: dict[str, str], write: SecretWriter
) -> dict[str, Any]:
    """Store the owner's values for exactly the card's fields; the card's result keeps
    the keys only."""
    keys = [field["key"] for field in row.payload["fields"]]
    if set(values) != set(keys):
        raise LonoraError("owner_action_secret_values_invalid", 422)
    if row.payload["destination"] == BROKER:
        # The broker layer's own writer; the account is provisioned by the gateway, which
        # wakes the agent with the result (``lonora_trading.broker_provisioning``).
        names = {PASSWORD_FIELD: metaapi_password_name(row.id), TOKEN_FIELD: METAAPI_TOKEN}
        token_saved = await session.scalar(
            select(SecretRow.id).where(
                SecretRow.owner_id == row.owner_id,
                SecretRow.scope == BROKER,
                SecretRow.name == METAAPI_TOKEN,
            )
        )
        for key in keys:
            if key == TOKEN_FIELD and token_saved is not None:
                # A card raised before the token was saved never replaces it: live
                # connections use it. Replacing the token is its own action (9.3).
                continue
            await write(session, names[key], values[key], BROKER)
        return {
            "saved": keys,
            "destination": BROKER,
            "provisioning": "pending",
            "started_at": utcnow().isoformat(),
        }
    for key in keys:
        await write(session, key, values[key], row.payload["destination"])
    return {"saved": keys, "destination": row.payload["destination"]}


def saved_prompt(row: OwnerActionRow) -> str:
    """The agent's next run after the owner saved: the keys (checked names), never a
    value and never the agent's own label."""
    if row.payload["destination"] == BROKER:
        return broker_prompt(row)
    keys = ", ".join(row.result.get("saved", []))
    return (
        f"The owner saved {keys} on your Secret card as {row.result.get('destination')} "
        "secrets; you never see their values. Continue the work that needed them now, then "
        "tell the owner in one line what you did."
    )


def broker_prompt(row: OwnerActionRow) -> str:
    """Fixed text and broker-observed facts only, after provisioning finished."""
    result = row.result
    if result.get("provisioning") != "connected":
        # The login was checked as digits; the failure code is the server's own word.
        token = (
            " The saved MetaApi API token itself was refused. It cannot be replaced from chat"
            " yet; never ask the owner for it in chat."
            if result.get("code") == "broker_token_rejected"
            else ""
        )
        return (
            f"Connecting the owner's account {row.payload['account']['login']} failed: "
            f"{result.get('code')}.{token} You never see "
            "the password or token. Tell the owner in one line what went wrong and what you "
            "need; to try again, call broker_connect, which shows a new card."
        )
    facts: dict[str, Any] = result.get("account") or {}
    if facts.get("balance") is None:
        state = "Its balance is not readable yet; read it with account_read shortly."
    else:
        trading = (
            "trading is allowed"
            if facts.get("trade_allowed") and not facts.get("investor_mode")
            else "trading is NOT allowed (an investor password or a read-only account)"
        )
        state = f"Balance {facts['balance']} {facts.get('currency')}; {trading}."
    observed: dict[str, Any] = result.get("observed") or {}
    named = f"account {observed.get('login')} on {observed.get('server')}"
    return (
        f"The owner's {named} is connected and deployed at MetaApi as connection "
        f"{result.get('connection_id')}. {state} Report this to the owner in one line."
    )
