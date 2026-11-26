"""The Secret card (VISION.md 7.2, 10.3): how a credential reaches Lonora.

An agent's own card: the agent chooses its label and fields (each a key, the name agents
use, and a label the owner reads), and the values are saved as the owner's workspace
secrets under those keys.

A connecting card (``connect``): the server sets its fields and its destination, and
saving it creates the connection. The non-secret details (a name) come from the
owner's words in chat through the agent's call and are shown on the card as facts. An
address (an MCP server's, a feed's or a calendar's) may carry a key, so the owner types
it into the card. Its values are workspace secrets. A model provider's key is saved under
the provider's usual name (``ANTHROPIC_API_KEY``) and recorded for the router, with an
OpenAI-compatible endpoint's base URL, which the owner types beside it
(``lonora_db.model_credentials``).

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
from lonora_contracts.model_routing import PROVIDER_KEY_NAMES
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
    "model_provider": ((("API_KEY", "api_key", True, True),), WORKSPACE),
}
# An OpenAI-compatible endpoint's card also asks for its base URL, typed with the key.
ENDPOINT_FIELDS = (("URL", "server_url", True, False), ("API_KEY", "api_key", True, True))
# The name the owner reads for a fixed model provider; an endpoint is shown by its URL.
PROVIDER_NAMES = {
    "anthropic": "Anthropic",
    "openai": "OpenAI",
    "deepseek": "DeepSeek",
    "openrouter": "OpenRouter",
    "zai": "Z.ai",
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
    if target == "model_provider":
        # The provider's key, saved under its usual name and recorded for the router;
        # an endpoint's base URL is typed into the card with it.
        provider = proposal.name
        assert provider is not None
        details = {"provider": provider}
        if provider in PROVIDER_NAMES:
            details["name"] = PROVIDER_NAMES[provider]
        else:
            asked = ENDPOINT_FIELDS
        return subject_of(target, provider), {
            "label": None,
            "connect": target,
            "service": None,
            "details": details,
            "fields": [
                {"key": key, "label": None, "secret": masked, "role": role, "required": required}
                for key, role, required, masked in asked
            ],
            "destination": destination,
        }
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
        if set(keys) & set(PROVIDER_KEY_NAMES.values()):
            # A card raised before these names were reserved: only a model_provider card
            # sets the router's key.
            return "secret_name_reserved"
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
        if payload.get("server_from"):
            # Saving it moves the connection off this server: the owner sees that too.
            facts["server_from"] = payload["server_from"]
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
    elif payload["connect"] == "model_provider":
        # One name, the provider's usual one; saving replaces the key saved there.
        name = PROVIDER_KEY_NAMES[payload["details"]["provider"]]
        held = await session.scalar(
            select(SecretRow.id).where(
                SecretRow.owner_id == owner_id,
                SecretRow.scope == WORKSPACE,
                SecretRow.name == name,
            )
        )
        facts["saves_as"] = [name]
        facts["replaces"] = [name] if held is not None else []
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
    if target == "model_provider":
        provider = row.payload["details"]["provider"]
        catalog, key = row.result.get("catalog"), row.result.get("key")
        if key == "rejected":
            return (
                f"The owner connected the model provider {provider} on your Secret card; you "
                "never see its key. The provider rejected the key: tell the owner in one line "
                "that it did not work and that a new Secret card replaces it."
            )
        if key == "accepted":
            listed = "The provider accepted the key."
        elif key is not None:
            listed = "The key could not be checked yet; say so."
        elif isinstance(catalog, int):
            listed = f"Its catalog was read: {catalog} models."
        else:
            listed = "Its catalog could not be read yet; say so."
        return (
            f"The owner connected the model provider {provider} on your Secret card; you "
            f"never see its key. {listed} Call model_list and tell the owner in one line "
            "which models became available."
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


# What a broker failure means, said as what MetaApi and Lonora observed (never a cause
# MetaApi did not report), with the owner's fix. Every code that can end a broker card or
# its first account read has one (tests/test_secret_card.py walks them): a wake with a
# bare code had the model invent a cause (production, 2026-11-19). The system alerts read
# only what was observed (LOGIN_OBSERVED): an account that was trading needs no
# first-connect causes.
LOGIN_CHECK = (
    "The usual causes: a wrong password, or a server name the account is no longer on "
    "(Exness moves demo accounts between Exness-MT5TrialNN servers). Ask the owner for the "
    "server name exactly as his MT5 app shows it now. For another server, call "
    "broker_connect with it; for the same server, a new password goes through broker_manage "
    "rotate_password when the connection is saved, or broker_connect when it is not."
)
LOGIN_OBSERVED = {
    "broker_login_not_established": "MetaApi has the account's terminal deployed, but it "
    "is not logged in to the broker: MetaApi reports it DISCONNECTED and gives no reason, "
    "so Lonora cannot see why.",
    "broker_login_rejected": "MetaApi reports the broker refusing the terminal's login "
    "(DISCONNECTED_FROM_BROKER); the broker's server may also be down for a while.",
}
BROKER_CAUSES = {
    **{code: observed + " " + LOGIN_CHECK for code, observed in LOGIN_OBSERVED.items()},
    "broker_password_rejected": "MetaApi could not log in to the broker with this login, "
    "password and server name; it does not say which is wrong. " + LOGIN_CHECK,
    "broker_server_not_found": "MetaApi does not know this server name. Ask the owner for "
    "the server name exactly as his MT5 app shows it now, then call broker_connect with it.",
    "broker_connect_timeout": "MetaApi did not have the account's terminal deployed and "
    "logged in to the broker within the time Lonora waits; nothing at the broker was "
    "confirmed.",
    "broker_provisioning_busy": "When Lonora's wait ran out, MetaApi was still deploying, "
    "redeploying or undeploying the account's terminal: it reported the account as deploying "
    "or undeploying, or refused Lonora's request because the account was in the process of "
    "being deployed, redeployed or undeployed. Nothing at the broker judged the login. Try "
    "again in a few minutes.",
    # MetaApi's answers to Lonora's requests about the account at MetaApi.
    "broker_provisioning_rejected": "MetaApi refused the request and gave no reason Lonora "
    "can show; nothing at the broker judged the login, so do not name a cause.",
    "broker_provisioning_conflict": "MetaApi refused the request as conflicting with the "
    "account's state at MetaApi and gave no reason Lonora can show; nothing at the broker "
    "judged the login. Try again in a few minutes.",
    "broker_provisioning_timeout": "MetaApi did not answer within the time Lonora waits, so "
    "whether it carried out the request is not known; nothing at the broker judged the "
    "login. Try again in a few minutes.",
    "broker_provisioning_unavailable": "MetaApi could not be reached or gave no usable "
    "answer, so whether it carried out the request is not known; nothing at the broker "
    "judged the login. Try again in a few minutes.",
    "broker_rate_limited": "MetaApi refused the request because Lonora made too many (rate "
    "limited); this says nothing about the login. Try again in a few minutes.",
    "broker_token_rejected": "MetaApi refused the MetaApi API token (unauthorized or "
    "forbidden), or the saved token cannot manage MetaApi accounts (it is not in the form of "
    "a MetaApi API access token, so the MetaApi SDK refused to send that request with it); "
    "nothing at the broker judged the login.",
    "broker_account_not_found": "MetaApi answered that it has no account with the id Lonora "
    "uses, for the MetaApi API token used; this says nothing about the login.",
    "broker_platform_required": "The card names no MT4 or MT5 platform, so Lonora created no "
    "MetaApi account; nothing at the broker judged the login.",
    "broker_provisioning_failed": "Lonora's last try at this step, after its wait ran out, "
    "ended in an error Lonora cannot show; this says nothing about the login.",
    # Lonora's own checks before or after MetaApi's answer.
    "broker_secret_required": "A credential this step needs (the trading password or the "
    "MetaApi API token) was not in Lonora's broker store, so the step was not taken; this "
    "says nothing about the login.",
    "broker_connect_in_progress": "Another saved card for this login and server was still "
    "connecting it, so this card sent nothing to MetaApi; that card reports its own outcome.",
    "broker_account_already_connected": "Lonora already has a saved connection for this "
    "account, so it saved no second one; this says nothing about the login.",
    "broker_identity_mismatch": "MetaApi's stored record of the account names another login "
    "or server than this card, so Lonora saved no connection; nothing at the broker judged "
    "the login.",
    "broker_identity_unavailable": "MetaApi's stored record of the account gave no login, "
    "server and platform Lonora could check, so Lonora saved no connection; this says "
    "nothing about the login.",
    # Reading the account through MetaApi (the connection's check and its first read).
    "broker_credentials_rejected": "MetaApi refused the MetaApi API token when Lonora read "
    "the account (unauthorized or forbidden); this says nothing about the broker login.",
    "broker_account_undeployed": "MetaApi reported the account's terminal as not deployed "
    "when Lonora read it; this says nothing about the login.",
    "broker_account_not_ready": "MetaApi reported the account's terminal as neither deployed "
    "nor undeployed (still deploying or undeploying, for example) when Lonora read it, so "
    "nothing was read through it; this says nothing about the login.",
    "broker_candles_invalid": "MetaApi answered Lonora's read of the account with data Lonora "
    "could not read as valid; this says nothing about the login.",
    "broker_connection_timeout": "MetaApi did not answer Lonora's read of the account within "
    "the time Lonora waits; this says nothing about the login.",
    "broker_connection_unavailable": "MetaApi could not be reached, or gave no usable "
    "answer, when Lonora read the account; this says nothing about the login.",
    "broker_request_rejected": "MetaApi refused Lonora's read of the account and gave no "
    "reason Lonora can show; this says nothing about the login, so do not name a cause.",
    "broker_connection_closed": "The terminal connection Lonora read through closed before "
    "it answered; this says nothing about the login.",
    "broker_disabled": "The saved connection is disabled in Lonora, so nothing was read "
    "through it; this says nothing about the login.",
    "broker_connection_changed": "A broker connection changed in Lonora while this step ran "
    "(one was added or removed, or its credential changed), so Lonora did not use the "
    "step's result; this says nothing about the login.",
    "broker_sessions_not_found": "The saved connection this step needs is no longer in "
    "Lonora, so the step was not taken; this says nothing about the login.",
    # Lonora's broker store, read for the trading password or the MetaApi API token.
    "secret_not_found": "A credential this step reads (the trading password or the MetaApi "
    "API token) was not among the owner's saved credentials when Lonora read it, so nothing "
    "that needed it was sent; this says nothing about the login.",
    "secret_scope_forbidden": "A credential this step reads (the trading password or the "
    "MetaApi API token) is saved in Lonora but not as a broker credential, so Lonora did not "
    "use it and sent nothing that needed it; this says nothing about the login.",
    "secret_decryption_failed": "A credential this step reads (the trading password or the "
    "MetaApi API token) could not be decrypted with Lonora's current encryption key, so "
    "nothing that needed it was sent; this says nothing about the login.",
    # Changing a saved connection's password or token.
    "broker_not_metaapi": "The saved connection is not a MetaApi connection with a token, so "
    "Lonora sent nothing to MetaApi.",
    "broker_operation_unsettled": "An operation on this account has no confirmed outcome "
    "yet, so Lonora did not go on with the change; it can once that is settled.",
    "broker_token_mismatch": "The new MetaApi API token does not see every connected MetaApi "
    "account, so Lonora kept the tokens the connections use.",
    "broker_rotation_incomplete": "MetaApi took the new trading password (and the new server, "
    "for a move), but Lonora could not record the change, so the terminal was not "
    "redeployed with it. Rotate again with broker_manage.",
    "broker_rotation_superseded": "While this card waited for MetaApi to take a redeploy, "
    "another new-password card for the same connection replaced the password, or the "
    "connection was disconnected, so the password from this card is no longer the "
    "connection's and Lonora did not redeploy the terminal with it; this says nothing about "
    "the login.",
    "broker_credential_change_failed": "The change ended in an error Lonora cannot show, so "
    "how far it got is not known.",
}
# After every outcome but a confirmed connection: the model names no cause it was not given.
OBSERVED_ONLY = (
    "Name no cause beyond the text given here, and quote the account login exactly as written here."
)


def broker_prompt(row: OwnerActionRow) -> str:
    """Fixed text and observed facts only, after provisioning finished."""
    result = row.result
    purpose = row.payload.get("purpose", CONNECT)
    if purpose != CONNECT:
        done = {
            ROTATE_PASSWORD: "The new trading password is stored at MetaApi and the terminal "
            "is redeploying with it.",
            REPLACE_TOKEN: "The new MetaApi token now serves every connected account.",
        }[purpose]
        moved = row.payload["account"]["server"] if row.payload.get("server_from") else None
        if moved:
            # What MetaApi stored before the move, read when it was made.
            was = str(result.get("server_was") or "")
            done = (
                f"MetaApi already had the account on server {moved}; the new trading password "
                "is stored there and the terminal is redeploying with it."
                if was.casefold() == moved.casefold()
                else f"MetaApi now has the account on server {moved}"
                + (f" (it had {was})" if was else "")
                + " with the new trading password, and the terminal is redeploying with them."
            )
        if purpose == ROTATE_PASSWORD:
            done += " Whether the broker accepts the login shows only when account_read answers."
        if result.get("provisioning") == "connected":
            return done + " You never see it. Tell the owner in one line."
        cause = BROKER_CAUSES.get(str(result.get("code")))
        because = f"{result.get('code')}.{' ' + cause if cause else ''}"
        login = row.payload["account"]["login"]
        if result.get("password_stored") and result.get("code") != "broker_rotation_superseded":
            # Stored at MetaApi and recorded, but no redeploy with it was confirmed; nothing
            # else redeploys a terminal that is running.
            changed = "password and server" if moved else "password"
            return (
                f"The new trading {changed} of account {login} {'are' if moved else 'is'} "
                "stored at MetaApi and recorded, but no redeploy of the terminal with "
                f"{'them' if moved else 'it'} was confirmed: {because} Until the terminal is "
                f"redeployed, it logs in with the {changed} it was last deployed with; to "
                "redeploy it, call broker_manage rotate_password again, and the owner types "
                f"the same new password. You never see it. {OBSERVED_ONLY} Tell the owner in "
                "one line."
            )
        changing = (
            "Making the new MetaApi API token the one every MetaApi connection uses"
            if purpose == REPLACE_TOKEN
            else f"Changing the broker credential of account {login}"
        )
        return (
            f"{changing} failed: {because} You never see the values. "
            f"{OBSERVED_ONLY} Tell the owner in one line what went wrong."
        )
    observed: dict[str, Any] = result.get("observed") or {}
    named = f"account {observed.get('login')} on {observed.get('server')}"
    if result.get("provisioning") == "linked":
        # Reading starts only once MetaApi reported the terminal connected to the broker;
        # the read code says what was seen after that.
        cause = BROKER_CAUSES.get(str(result.get("read_code")))
        return (
            f"The owner's {named} is saved as connection {result.get('connection_id')}. "
            "MetaApi reported its terminal connected to the broker when the connection was "
            f"saved, but no account read answered in time ({result.get('read_code')}), so no "
            "balance was read. That login and server are MetaApi's stored record of the "
            "account, not a broker answer. "
            + (
                cause + " Tell the owner in one line that it is saved, that no balance could "
                "be read, and why; read it again with account_read later."
                if cause
                else "Tell the owner in one line that it is saved and no balance could be "
                "read yet; read it again with account_read later."
            )
            + " "
            + OBSERVED_ONLY
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
        cause = BROKER_CAUSES.get(str(result.get("code")))
        if result.get("password_stored") and not result.get("password_set"):
            # The account the token already had took this card's password, and no redeploy
            # with it was confirmed (production, 2026-11-19).
            cause = (cause + " " if cause else "") + (
                "MetaApi stores the password the owner typed on this card for the account, "
                "but no redeploy of its terminal with it was confirmed: until the terminal "
                "is redeployed, it logs in with the password it was last deployed with."
            )
        return (
            f"Connecting the owner's account {row.payload['account']['login']} failed: "
            f"{result.get('code')}.{token}{' ' + cause if cause else ''} You never see "
            f"the password or token. {OBSERVED_ONLY} Tell the owner in one line what went "
            "wrong and what you need; to try again, call broker_connect, which shows a new "
            "card."
        )
    facts: dict[str, Any] = result.get("account") or {}
    trading = (
        "trading is allowed"
        if facts.get("trade_allowed") and not facts.get("investor_mode")
        else "trading is NOT allowed (an investor password or a read-only account; if the "
        "owner typed the investor password, broker_manage rotate_password asks for the main "
        "(master) one)"
    )
    return (
        f"The owner's {named} is connected as connection {result.get('connection_id')}: "
        "its MetaApi terminal answered a read from the broker. Balance "
        f"{facts.get('balance')} {facts.get('currency')}; {trading}. Report this to the "
        "owner in one line."
    )
