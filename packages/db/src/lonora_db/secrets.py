"""Stored secrets by scope.

``broker`` holds broker passwords and the MetaApi token: only the execution door and
provisioning read it. ``provider`` holds model API keys and ``integration`` the tokens of
news feeds, web search, the calendar and MCP servers. ``workspace`` holds the owner's
secrets for agents to use by name in the workspace; its names are environment variable
names. A secret a connection uses is not deleted while the connection refers to it.
"""

import re

from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import BrokerSessionRow, IntegrationRow, McpConnectionRow, SecretRow

WORKSPACE = "workspace"
BROKER = "broker"
SCOPES = (BROKER, "provider", "integration", WORKSPACE)
WORKSPACE_NAME = re.compile(r"[A-Z][A-Z0-9_]{0,63}")
CONNECTIONS = (BrokerSessionRow, IntegrationRow, McpConnectionRow)


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


async def secret_in_use(session: AsyncSession, owner_id: str, secret_id: str) -> bool:
    """A broker, integration or MCP connection still refers to it."""
    for row_type in CONNECTIONS:
        used = await session.scalar(
            select(row_type.id)
            .where(
                row_type.owner_id == owner_id,
                row_type.payload["secret_id"].as_string() == secret_id,
            )
            .limit(1)
        )
        if used is not None:
            return True
    return False
