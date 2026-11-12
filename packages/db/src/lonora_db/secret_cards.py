"""The Secret card (VISION.md 7.2, 10.3): how a credential reaches Lonora.

An agent's own card: the agent chooses its label and fields (each a key, the name agents
use, and a label the owner reads), and the values are saved as the owner's workspace
secrets under those keys.

A connecting card (``connect``): the server sets its fields and its destination, and
saving it creates the connection. The non-secret details (a name, a MetaApi account id)
come from the owner's words in chat through the agent's call and are shown on the card
as facts. An address (an MCP server's, a feed's or a calendar's) may carry a key, so the
owner types it into the card. A broker's MetaApi token goes to the broker scope, read
only by the execution door and provisioning; every other value is a workspace secret.

The owner's values go straight to the encrypted store in the transaction that settles
the card; the card, its events and the conversation keep only the saved names.
"""

import hashlib
import re
from collections.abc import Awaitable, Callable
from typing import Any

from lonora_contracts.owner_actions import OwnerActionProposal
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import IntegrationRow, OwnerActionRow, SecretRow
from .secrets import WORKSPACE, WORKSPACE_NAME, secret_in_use

# Writes one value to the encrypted store in the caller's transaction; returns its id.
SecretWriter = Callable[[AsyncSession, str, str, str], Awaitable[str]]

BROKER = "broker"
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
    "broker": ((("METAAPI_TOKEN", "metaapi_token", True, True),), BROKER),
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
    if target == "broker":
        assert proposal.metaapi_account_id is not None
        details = {"metaapi_account_id": proposal.metaapi_account_id}
    else:
        name = proposal.name or DEFAULT_NAME.get(target)
        assert name is not None
        details = {"name": name}
    (named,) = details.values()
    return subject_of(target, named), {
        "label": None,
        "connect": target,
        "service": proposal.service,
        "details": details,
        "fields": [
            {"key": key, "label": None, "secret": masked, "role": role, "required": required}
            for key, role, required, masked in asked
        ],
        "destination": destination,
    }


async def secret_stale_reason(
    session: AsyncSession, owner_id: str, payload: dict[str, Any]
) -> str | None:
    """Checked when the card is raised and again when the owner saves it: web search
    needs one Brave key, and an agent's own card never replaces a value a connection
    uses (a feed's address saved under that name would then read another site)."""
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
    session: AsyncSession, owner_id: str, payload: dict[str, Any], agent_name: str | None
) -> dict[str, Any]:
    """What the card shows: its label or what it connects, its fields, where the values
    go and who asked; the workspace names its values are saved under, and for the
    agent's own card which of them would replace a saved secret (read now)."""
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
    elif payload["destination"] == WORKSPACE:
        names = await free_names(session, owner_id, payload["connect"], payload["details"]["name"])
        facts["saves_as"] = [names[str(field["key"])] for field in payload["fields"]]
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
        named = part if number == 1 else f"{part[:36].rstrip('_')}_{number}"
        names = {key: form.format(name=named) for key, form in SAVED_AS[target].items()}
        if not taken.intersection(names.values()):
            assert all(WORKSPACE_NAME.fullmatch(item) for item in names.values())
            return names
        number += 1


def saved_prompt(row: OwnerActionRow) -> str:
    """The agent's next run after the owner saved: never a value, and never a name the
    agent's words shaped (its keys, its label, or a saved name built from a name it
    gave): this text has system role."""
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
    return (
        f"The owner connected {target} on your Secret card; it is configured on the server "
        "and you never see its value. Continue the work that needed it now, then tell the "
        "owner in one line what you did."
    )
