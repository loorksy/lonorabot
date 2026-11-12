"""The Secret card (VISION.md 7.2, 10.3): how a credential reaches Lonora.

An agent's own card: the agent chooses its label and fields (each a key, the name agents
use, and a label the owner reads), and the values are saved as the owner's workspace
secrets under those keys.

A connecting card (``connect``): the server sets its one field and its destination, and
saving it creates the connection. The non-secret details (a name, an MCP server's URL, a
MetaApi account id) come from the owner's words in chat through the agent's call and are
shown on the card as facts. A broker's MetaApi token goes to the broker scope, read only
by the execution door and provisioning; every other value is a workspace secret.

The owner's values go straight to the encrypted store in the transaction that settles
the card; the card, its events and the conversation keep only the saved names.
"""

import hashlib
import re
from collections.abc import Awaitable, Callable
from typing import Any

from lonora_contracts.mcp import McpConnection
from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_core.user_error import LonoraError
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import IntegrationRow, OwnerActionRow, SecretRow
from .secrets import WORKSPACE, WORKSPACE_NAME

# Writes one value to the encrypted store in the caller's transaction; returns its id.
SecretWriter = Callable[[AsyncSession, str, str, str], Awaitable[str]]

BROKER = "broker"
# What a connecting card asks for: its one field (key, role, required, masked while
# typed: an address is shown, though it is stored encrypted) and where the value goes.
CONNECTING: dict[str, tuple[str, str, bool, bool, str]] = {
    "mcp_server": ("TOKEN", "token", False, True, WORKSPACE),
    "brave_search": ("API_KEY", "api_key", True, True, WORKSPACE),
    "news_feed": ("URL", "feed_url", True, False, WORKSPACE),
    "economic_calendar": ("URL", "feed_url", True, False, WORKSPACE),
    "broker": ("METAAPI_TOKEN", "metaapi_token", True, True, BROKER),
}
# The workspace name a connecting card's value is saved under ({name}: from the details).
SAVED_AS = {
    "mcp_server": "MCP_{name}_TOKEN",
    "brave_search": "BRAVE_API_KEY",
    "news_feed": "FEED_{name}_URL",
    "economic_calendar": "CALENDAR_{name}_URL",
}


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
    key, role, required, masked, destination = CONNECTING[target]
    details: dict[str, str] = {}
    if target == "mcp_server":
        assert proposal.url is not None
        details = {"name": proposal.name or "X", "url": proposal.url}
        try:
            McpConnection(name=details["name"], url=proposal.url, transport="http", enabled=True)
        except ValidationError:
            raise LonoraError("mcp_url_invalid", 422) from None
    elif target == "brave_search":
        details = {"name": proposal.name or "Brave Search"}
    elif target == "broker":
        assert proposal.metaapi_account_id is not None
        details = {"metaapi_account_id": proposal.metaapi_account_id.strip()}
    else:
        assert proposal.name is not None
        details = {"name": proposal.name.strip()}
    named = details.get("url") or details.get("metaapi_account_id") or details["name"]
    return subject_of(target, named), {
        "label": None,
        "connect": target,
        "service": proposal.service,
        "details": details,
        "fields": [
            {"key": key, "label": None, "secret": masked, "role": role, "required": required}
        ],
        "destination": destination,
    }


async def secret_stale_reason(
    session: AsyncSession, owner_id: str, payload: dict[str, Any]
) -> str | None:
    """Web search needs one Brave key: a second card for it is not raised."""
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
    session: AsyncSession, owner_id: str, payload: dict[str, Any], agent_name: str | None
) -> dict[str, Any]:
    """What the card shows: its label or what it connects, its fields, where the values
    go and who asked; for the agent's own card, the names its values are saved under and
    which of them would replace a saved secret (read now)."""
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
    return facts


def card_values(row: OwnerActionRow, values: dict[str, str]) -> dict[str, str]:
    """The owner's values for exactly the card's fields: every required one, no other."""
    fields = {field["key"]: field.get("required", True) for field in row.payload["fields"]}
    if not set(values) <= set(fields) or any(
        required and not values.get(key) for key, required in fields.items()
    ):
        raise LonoraError("owner_action_secret_values_invalid", 422)
    return {key: value for key, value in values.items() if value}


async def save_values(
    session: AsyncSession, row: OwnerActionRow, values: dict[str, str], write: SecretWriter
) -> dict[str, Any]:
    """An agent's own card: each value under its key; the result keeps the keys only."""
    values = card_values(row, values)
    keys = [field["key"] for field in row.payload["fields"]]
    for key in keys:
        await write(session, key, values[key], row.payload["destination"])
    return {"saved": keys, "destination": row.payload["destination"]}


def name_part(text: str) -> str:
    """A name in a saved secret's name: upper case letters, digits and single ``_``."""
    part = re.sub(r"_+", "_", re.sub(r"[^A-Z0-9]", "_", text.upper())).strip("_")
    return part[:40].rstrip("_") or "SOURCE"


async def free_name(session: AsyncSession, owner_id: str, target: str, name: str) -> str:
    """A workspace name for a connecting card's value that no saved secret has yet, so
    one connection's value never replaces another's."""
    base = SAVED_AS[target].format(name=name_part(name))
    taken = set(
        (
            await session.scalars(
                select(SecretRow.name).where(
                    SecretRow.owner_id == owner_id, SecretRow.scope == WORKSPACE
                )
            )
        ).all()
    )
    candidate, number = base, 1
    while candidate in taken:
        number += 1
        candidate = base[: 64 - len(str(number)) - 1] + "_" + str(number)
    assert WORKSPACE_NAME.fullmatch(candidate)
    return candidate


def saved_prompt(row: OwnerActionRow) -> str:
    """The agent's next run after the owner saved: checked names only, never a value
    and never the agent's own label."""
    saved = ", ".join(row.result.get("saved", []))
    target = row.payload.get("connect")
    if target is None:
        # Not the keys: they are the agent's own choice and this text has system role.
        return (
            "The owner saved the values on your Secret card, encrypted as workspace secrets "
            "under the keys you chose; you never see them. Tell the owner in one line what "
            "they are saved for."
        )
    review = row.result.get("review")
    if target == "mcp_server" and review in {"unread", "nothing_to_trust"}:
        reason = (
            "its tools could not be read yet"
            if review == "unread"
            else "none of its tools can be trusted (a tool that can trade or move money never runs)"
        )
        return (
            "The owner connected an MCP server (connection_id="
            f"{row.result.get('connection_id')}) on your Secret card; its credential stays on "
            f"the server. No review card followed: {reason}. Check it with mcp_tools now: if "
            "it lists tools to review, propose trust_source for this connection_id; otherwise "
            "tell the owner in one line what is wrong."
        )
    named = f" (saved as {saved})" if saved else ""
    return (
        f"The owner connected {target} on your Secret card{named}; it is configured on the "
        "server and you never see its value. Continue the work that needed it now, then "
        "tell the owner in one line what you did."
    )
