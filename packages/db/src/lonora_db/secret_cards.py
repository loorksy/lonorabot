"""The Secret card (VISION.md 7.2, 10.3): how a credential reaches Lonora.

An agent's own card: the agent chooses its label and fields (each a key, the name agents
use, and a label the owner reads), and the values are saved as the owner's workspace
secrets under those keys.

A connecting card (``connect``): the server sets its fields and its destination, and
saving it creates the connection. The non-secret details (a name) come from the
owner's words in chat through the agent's call and are shown on the card as facts. An
address (an MCP server's, a feed's or a calendar's) may carry a key, so the owner types
it into the card. Its values are workspace secrets.

A broker card (``broker_card_payload``): raised only by the broker tools, with fields the
server fixes (the trading password, the MetaApi API token). Its values go to the broker
scope, read only by the execution door and provisioning (7.2.3); the gateway provisions
the account and wakes the agent with the result.

The owner's values go straight to the encrypted store in the transaction that settles
the card; the card, its events and the conversation keep only the saved names.
"""

import hashlib
import re
from collections.abc import Awaitable, Callable
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import IntegrationRow, OwnerActionRow, SecretRow
from .secrets import (
    BROKER,
    METAAPI_TOKEN,
    WORKSPACE,
    WORKSPACE_NAME,
    metaapi_password_name,
    secret_in_use,
)

# Writes one value to the encrypted store in the caller's transaction; returns its id.
SecretWriter = Callable[[AsyncSession, str, str, str], Awaitable[str]]

# What a connecting card asks for: its fields (key, role, required, masked while typed:
# an address is shown, though it is stored encrypted) and where the values go.
CONNECTING: dict[str, tuple[tuple[tuple[str, str, bool, bool], ...], str]] = {
    "mcp_server": (
        (("URL", "server_url", True, False), ("TOKEN", "token", False, True)),
        WORKSPACE,
    ),
    "brave_search": ((("API_KEY", "api_key", True, True),), WORKSPACE),
    "news_feed": ((("URL", "feed_url", True, False),), WORKSPACE),
    "economic_calendar": ((("URL", "feed_url", True, False),), WORKSPACE),
}
# The workspace name each value of a connecting card is saved under ({name}: its name).
SAVED_AS: dict[str, dict[str, str]] = {
    "mcp_server": {"URL": "MCP_{name}_URL", "TOKEN": "MCP_{name}_TOKEN"},
    "brave_search": {"API_KEY": "BRAVE_API_KEY"},
    "news_feed": {"URL": "FEED_{name}_URL"},
    "economic_calendar": {"URL": "CALENDAR_{name}_URL"},
}
# The name a connecting card gets when the agent gives none.
DEFAULT_NAME = {"mcp_server": "X", "brave_search": "Brave Search"}


def subject_of(kind: str, named: str) -> str:
    """The record a card acts on, within the subject column whatever the keys or the
    address: what it saves to and a digest of what it names."""
    return "secret:" + kind + ":" + hashlib.sha256(named.encode()).hexdigest()[:40]


def secret_card_payload(proposal: OwnerActionProposal) -> tuple[str, dict[str, Any]]:
    """The card's stored effect: the agent's own fields, or a connecting card's."""
    if proposal.target is None:
        assert proposal.label is not None and proposal.secret_fields is not None
        fields: list[dict[str, Any]] = [
            {**field.model_dump(mode="json"), "role": None, "required": True}
            for field in proposal.secret_fields
        ]
        keys = sorted(field.key for field in proposal.secret_fields)
        return subject_of(WORKSPACE, ",".join(keys)), {
            "label": proposal.label,
            "connect": None,
            "fields": fields,
            "destination": WORKSPACE,
        }
    target = proposal.target
    asked, destination = CONNECTING[target]
    name = proposal.name or DEFAULT_NAME.get(target)
    assert name is not None
    return subject_of(target, name), {
        "label": None,
        "connect": target,
        "service": proposal.service,
        "details": {"name": name},
        "fields": [
            {"key": key, "label": None, "secret": masked, "role": role, "required": required}
            for key, role, required, masked in asked
        ],
        "destination": destination,
    }


# A broker-destination card (7.2.3) is raised only by the connect tool, which fixes its
# fields: the trading password, and the MetaApi API token while none is saved.
PASSWORD_FIELD = "PASSWORD"
TOKEN_FIELD = "METAAPI_TOKEN"


# What a broker card is for: connect an account, store its new password at MetaApi, or
# replace the owner's MetaApi token under every connection (9.2, 9.3).
CONNECT, ROTATE_PASSWORD, REPLACE_TOKEN = "connect", "rotate_password", "replace_token"


def broker_card_payload(
    *,
    login: str,
    server: str,
    platform: str,
    token_needed: bool,
    purpose: str = CONNECT,
    connection_id: str | None = None,
) -> tuple[str, dict[str, Any]]:
    """A broker card for one trading account (the token card names the account it was
    asked from). The login and server are shown as server facts, so the owner sees which
    account a password is for."""
    fields: list[dict[str, Any]] = []
    if purpose != REPLACE_TOKEN:
        fields.append({"key": PASSWORD_FIELD, "label": "Trading password", "secret": True})
    if token_needed or purpose == REPLACE_TOKEN:
        fields.append({"key": TOKEN_FIELD, "label": "MetaApi API token", "secret": True})
    payload: dict[str, Any] = {
        "label": login + " @ " + server,
        "fields": fields,
        "destination": BROKER,
        "account": {"login": login, "server": server, "platform": platform},
    }
    if purpose != CONNECT:
        payload["purpose"], payload["connection_id"] = purpose, connection_id
    return "secret:broker:" + purpose + ":" + server.casefold() + ":" + login, payload


async def secret_stale_reason(
    session: AsyncSession, owner_id: str, payload: dict[str, Any]
) -> str | None:
    """Checked when the card is raised and again when the owner saves it: web search
    needs one Brave key, and an agent's own card never replaces a value a connection
    uses (a feed's address saved under that name would then read another site)."""
    if payload["destination"] == BROKER:
        return None  # Provisioning checks a broker card's values with MetaApi.
    if payload.get("connect") is None:
        keys = [str(field["key"]) for field in payload["fields"]]
        saved = await session.scalars(
            select(SecretRow.id).where(
                SecretRow.owner_id == owner_id,
                SecretRow.scope == WORKSPACE,
                SecretRow.name.in_(keys),
            )
        )
        for secret_id in saved.all():
            if await secret_in_use(session, owner_id, secret_id):
                return "secret_name_in_use"
        return None
    if payload.get("connect") != "brave_search":
        return None
    rows = await session.scalars(select(IntegrationRow).where(IntegrationRow.owner_id == owner_id))
    configured = any(
        row.payload.get("type") == "brave_search"
        and row.payload.get("enabled")
        and row.payload.get("secret_id")
        for row in rows
    )
    return "credential_already_configured" if configured else None


async def secret_facts(
    session: AsyncSession, row: OwnerActionRow, agent_name: str | None
) -> dict[str, Any]:
    """What the card shows: its label or what it connects, its fields, where the values
    go and who asked; the workspace names its values are saved under, and for the
    agent's own card which of them would replace a saved secret. A waiting card reads
    them now; a settled one shows the names it saved and replaces nothing."""
    owner_id, payload = row.owner_id, row.payload
    facts: dict[str, Any] = {
        "label": payload.get("label"),
        "connect": payload.get("connect"),
        "service": payload.get("service"),
        "details": payload.get("details", {}),
        "fields": payload["fields"],
        "destination": payload["destination"],
        "agent_name": agent_name,
        "saves_as": [],
        "replaces": [],
    }
    if payload.get("account") is not None:
        # A broker card: the account its values are for. They go to the broker layer,
        # never under a workspace name.
        facts["account"] = payload["account"]
        facts["purpose"] = payload.get("purpose", CONNECT)
        return facts
    if row.status != "pending":
        facts["saves_as"] = [str(name) for name in row.result.get("saved", [])]
        return facts
    if payload.get("connect") is None:
        keys = [str(field["key"]) for field in payload["fields"]]
        saved = set(
            (
                await session.scalars(
                    select(SecretRow.name).where(
                        SecretRow.owner_id == owner_id,
                        SecretRow.scope == WORKSPACE,
                        SecretRow.name.in_(keys),
                    )
                )
            ).all()
        )
        facts["saves_as"] = keys
        facts["replaces"] = [key for key in keys if key in saved]
    elif payload["destination"] == WORKSPACE:
        target = payload["connect"]
        # A card converted from the credential card (0071) has no details.
        name = payload.get("details", {}).get("name") or DEFAULT_NAME.get(target) or target
        names = await free_names(session, owner_id, target, name)
        facts["saves_as"] = [names[str(field["key"])] for field in payload["fields"]]
    return facts


# A connecting card's key or token is sent in an HTTP header: visible ASCII only.
HEADER_ROLES = {"token", "api_key"}


def card_values(row: OwnerActionRow, values: dict[str, str]) -> dict[str, str]:
    """The owner's values for exactly the card's fields: every required one, no other.
    A connecting card's address, key or token is trimmed (a paste often adds a space or
    a line break); a key or token with a character no header can carry is refused."""
    fields = {field["key"]: field for field in row.payload["fields"]}
    cleaned = {
        key: value.strip() if fields.get(key, {}).get("role") else value
        for key, value in values.items()
    }
    if not set(cleaned) <= set(fields) or any(
        field.get("required", True) and not cleaned.get(key) for key, field in fields.items()
    ):
        raise LonoraError("owner_action_secret_values_invalid", 422)
    for key, value in cleaned.items():
        if fields[key].get("role") in HEADER_ROLES and not all(
            "!" <= char <= "~" for char in value
        ):
            raise LonoraError("owner_action_secret_value_unsendable", 422)
    return {key: value for key, value in cleaned.items() if value}


async def save_values(
    session: AsyncSession, row: OwnerActionRow, values: dict[str, str], write: SecretWriter
) -> dict[str, Any]:
    """An agent's own card: each value under its key; a broker card: its values in the
    broker scope. The result keeps the keys only."""
    values = card_values(row, values)
    keys = [field["key"] for field in row.payload["fields"]]
    if row.payload["destination"] == BROKER:
        # The broker layer's own writer; the account is provisioned by the gateway, which
        # wakes the agent with the result (``lonora_trading.broker_provisioning``).
        replacing = row.payload.get("purpose") == REPLACE_TOKEN
        names = {
            PASSWORD_FIELD: metaapi_password_name(row.id),
            # A new token waits under its own name until the gateway checked it sees
            # every connected account; only then does it replace the owner's token.
            TOKEN_FIELD: "metaapi_token_next:" + row.id if replacing else METAAPI_TOKEN,
        }
        token_saved = await session.scalar(
            select(SecretRow.id).where(
                SecretRow.owner_id == row.owner_id,
                SecretRow.scope == BROKER,
                SecretRow.name == METAAPI_TOKEN,
            )
        )
        for key in keys:
            if key == TOKEN_FIELD and token_saved is not None and not replacing:
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


def name_part(text: str) -> str:
    """A name in a saved secret's name: upper case letters, digits and single ``_``."""
    part = re.sub(r"_+", "_", re.sub(r"[^A-Z0-9]", "_", text.upper())).strip("_")
    return part[:40].rstrip("_") or "SOURCE"


async def free_names(
    session: AsyncSession, owner_id: str, target: str, name: str
) -> dict[str, str]:
    """The workspace names a connecting card's values are saved under, none of them
    held by a saved secret yet, so one connection's value never replaces another's. One
    card's values share one name part: ``MCP_DESK_2_URL`` with ``MCP_DESK_2_TOKEN``."""
    taken = set(
        (
            await session.scalars(
                select(SecretRow.name).where(
                    SecretRow.owner_id == owner_id, SecretRow.scope == WORKSPACE
                )
            )
        ).all()
    )
    part, number = name_part(name), 1
    while True:
        # The number goes into the name part, or at the end of a name without one.
        suffix = "" if number == 1 else f"_{number}"
        named = part if number == 1 else part[:36].rstrip("_") + suffix
        names = {
            key: form.format(name=named) if "{name}" in form else form + suffix
            for key, form in SAVED_AS[target].items()
        }
        if not taken.intersection(names.values()):
            assert all(WORKSPACE_NAME.fullmatch(item) for item in names.values())
            return names
        number += 1


def saved_prompt(row: OwnerActionRow) -> str:
    """The agent's next run after the owner saved: never a value, and never a name the
    agent's words shaped (its keys, its label, or a saved name built from a name it
    gave): this text has system role."""
    if row.payload["destination"] == BROKER:
        return broker_prompt(row)
    target = row.payload.get("connect")
    if target is None:
        # Not the keys: they are the agent's own choice and this text has system role.
        return (
            "The owner saved the values on your Secret card, encrypted as workspace secrets "
            "under the keys you chose; you never see them. Tell the owner in one line what "
            "they are saved for."
        )
    if target == "mcp_server":
        return (
            "The owner connected an MCP server (connection_id="
            f"{row.result.get('connection_id')}) on your Secret card; its credential stays on "
            "the server. Its tools run only once the owner trusts it: tell him in one line to "
            "name the server in chat (then call mcp_trust first in that run) or review it in "
            "Capabilities."
        )
    return (
        f"The owner connected {target} on your Secret card; it is configured on the server "
        "and you never see its value. Continue the work that needed it now, then tell the "
        "owner in one line what you did."
    )


def broker_prompt(row: OwnerActionRow) -> str:
    """Fixed text and broker-observed facts only, after provisioning finished."""
    result = row.result
    purpose = row.payload.get("purpose", CONNECT)
    if purpose != CONNECT:
        done = {
            ROTATE_PASSWORD: "The new trading password is stored at MetaApi and the terminal "
            "is redeploying with it.",
            REPLACE_TOKEN: "The new MetaApi token now serves every connected account.",
        }[purpose]
        if result.get("provisioning") == "connected":
            return done + " You never see it. Tell the owner in one line."
        if result.get("code") == "broker_rotation_incomplete":
            return (
                "MetaApi may already hold the new trading password, but Lonora could not record "
                "it. Rotate again with broker_manage. You never see it. Tell the owner in one "
                "line."
            )
        if result.get("code") == "broker_redeploy_failed":
            return (
                "The new trading password is stored at MetaApi and recorded, but redeploying "
                "the terminal with it failed; it reconnects on MetaApi's next deploy. You "
                "never see it. Tell the owner in one line."
            )
        return (
            f"Changing the broker credential failed: {result.get('code')}. Nothing changed. "
            "You never see the values. Tell the owner in one line what went wrong."
        )
    if result.get("provisioning") != "connected":
        # The login was checked as digits; the failure code is the server's own word.
        token = ""
        if result.get("code") == "broker_token_rejected":
            token = (
                " The saved MetaApi API token itself was refused. Live connections still use"
                " it: ask the owner for a new one with broker_manage (action replace_token),"
                " never in chat."
                if result.get("token_kept")
                else " The MetaApi API token was refused and is forgotten: call broker_connect"
                " again, and its card asks the owner for a new token. Never ask in chat."
            )
        if result.get("code") == "broker_legacy_connection_unreadable":
            token = (
                " A MetaApi connection saved earlier (the one without a broker identity in"
                " list_accounts) can no longer be read at MetaApi, so it may be this same"
                " account. With the owner's word, remove it with broker_manage (action"
                " disconnect), then call broker_connect again."
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
