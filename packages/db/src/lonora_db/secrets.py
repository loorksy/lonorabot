"""Stored secrets by scope.

``broker`` holds broker passwords and the MetaApi token: only the execution door and
provisioning read it. ``provider`` holds model API keys and ``integration`` the tokens of
news feeds, web search, the calendar and MCP servers. ``workspace`` holds the owner's
secrets for agents to use by name in the workspace, among them what a Secret card saved
for a connection; its names are environment variable names. A secret a connection uses
is not deleted while the connection refers to it.
"""

import re
from typing import Any

from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import BrokerSessionRow, IntegrationRow, McpConnectionRow, SecretRow

WORKSPACE = "workspace"
BROKER = "broker"
# The owner's one MetaApi API token (scope ``broker``); connections made from chat name it.
METAAPI_TOKEN = "metaapi_token"
SCOPES = (BROKER, "provider", "integration", WORKSPACE)
WORKSPACE_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
# Where a connection names its secrets: an MCP server saved from a Secret card also
# names the secret that holds its address.
REFERENCES = (
    (BrokerSessionRow, ("secret_id",)),
    (IntegrationRow, ("secret_id",)),
    (McpConnectionRow, ("secret_id", "url_secret_id")),
)


def require_scope(name: str, scope: str) -> None:
    if scope not in SCOPES:
        raise LonoraError("secret_scope_invalid", 422)
    if scope == WORKSPACE and not WORKSPACE_NAME.fullmatch(name):
        raise LonoraError("secret_name_invalid", 422)


async def secret_metadata(session: AsyncSession, owner_id: str, scope: str) -> list[dict[str, str]]:
    rows = (
        await session.scalars(
            select(SecretRow)
            .where(SecretRow.owner_id == owner_id, SecretRow.scope == scope)
            .order_by(SecretRow.name)
        )
    ).all()
    return [{"id": r.id, "name": r.name, "updated_at": r.updated_at.isoformat()} for r in rows]


def metaapi_password_name(card_id: str) -> str:
    """The broker secret of the password the owner saved on one connect card."""
    return "metaapi_password:" + card_id


async def secret_in_use(session: AsyncSession, owner_id: str, secret_id: str) -> bool:
    """A broker, integration or MCP connection still refers to it (a broker connection
    also by the password it was provisioned with)."""
    password = await session.scalar(
        select(BrokerSessionRow.id)
        .where(
            BrokerSessionRow.owner_id == owner_id,
            BrokerSessionRow.state["password_secret_id"].as_string() == secret_id,
        )
        .limit(1)
    )
    if password is not None:
        return True
    for row_type, keys in REFERENCES:
        for key in keys:
            used = await session.scalar(
                select(row_type.id)
                .where(
                    row_type.owner_id == owner_id,
                    row_type.payload[key].as_string() == secret_id,
                )
                .limit(1)
            )
            if used is not None:
                return True
    return False


async def delete_secret(session: AsyncSession, owner_id: str, secret_id: str) -> None:
    """The one deletion of a stored secret, for ``DELETE /secrets/{secret_id}`` and for
    the owner's word in chat: refused while a connection still uses it."""
    row = await session.get(SecretRow, secret_id, with_for_update=True)
    if row is None or row.owner_id != owner_id:
        raise LonoraError("secret_not_found", 404)
    if await secret_in_use(session, owner_id, secret_id):
        raise LonoraError("secret_in_use", 409)
    await session.delete(row)


async def workspace_secrets(session: AsyncSession, owner_id: str) -> list[dict[str, Any]]:
    """The owner's workspace secrets by name, never a value, with the connections that use
    each (a feed, a calendar, web search, an MCP server): what the owner may ask about."""
    rows = (
        await session.scalars(
            select(SecretRow)
            .where(SecretRow.owner_id == owner_id, SecretRow.scope == WORKSPACE)
            .order_by(SecretRow.name)
        )
    ).all()
    users: dict[str, list[dict[str, str]]] = {row.id: [] for row in rows}
    for row_type, keys in REFERENCES:
        if row_type is BrokerSessionRow:
            continue  # A broker session names a broker secret, never a workspace one.
        connections = await session.scalars(select(row_type).where(row_type.owner_id == owner_id))
        for connection in connections:
            kind = "mcp_server" if row_type is McpConnectionRow else connection.payload["type"]
            for key in keys:
                secret_id = connection.payload.get(key)
                if secret_id in users:
                    users[secret_id].append({"kind": kind, "name": connection.payload["name"]})
    return [
        {"name": row.name, "updated_at": row.updated_at.isoformat(), "used_by": users[row.id]}
        for row in rows
    ]
