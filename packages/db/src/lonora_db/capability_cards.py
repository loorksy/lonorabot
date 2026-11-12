"""Credential cards: how a missing account or credential reaches the owner in chat.

``connect_credential`` offers a secure form in the conversation. The client posts the
value straight to the owner API (``/integrations/secrets``, ``/integrations``, ``/mcp``
or ``/trading/connections``); the card only learns which resource was connected. No
value ever reaches the card, the transcript, an event or an agent: agents see
"configured". Trusting a source is no card: the owner's own words in chat do it
(``lonora_tools.source_trust``).

Everything a card shows is read here from records (the connection's saved name), never
model prose.
"""

from typing import Any

from lonora_core.user_error import LonoraError
from lonora_security.network import endpoint_sha256
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import BrokerSessionRow, IntegrationRow, McpConnectionRow, OwnerActionRow

CREDENTIAL_TARGETS = ("mcp_server", "news_feed", "brave_search", "economic_calendar", "broker")
# What each target's form creates, and the resource the decision names.
TARGET_RESOURCE = {
    "mcp_server": "mcp",
    "news_feed": "integration",
    "brave_search": "integration",
    "economic_calendar": "integration",
    "broker": "broker",
}


def credential_payload(target: str, service: str | None) -> tuple[str, dict[str, Any]]:
    if target not in CREDENTIAL_TARGETS or (service is not None and target != "mcp_server"):
        raise LonoraError("owner_action_fields_invalid", 422)
    return "credential:" + target + (":" + service if service else ""), {
        "target": target,
        "service": service,
    }


async def _connection(
    session: AsyncSession, owner_id: str, connection_id: str
) -> McpConnectionRow | None:
    row = await session.get(McpConnectionRow, connection_id)
    return row if row is not None and row.owner_id == owner_id else None


def current_endpoint(row: McpConnectionRow) -> str | None:
    try:
        return endpoint_sha256(str(row.payload.get("url") or ""))
    except LonoraError:
        return None


async def credential_not_needed(
    session: AsyncSession, owner_id: str, payload: dict[str, Any]
) -> str | None:
    """Why an agent need not offer this form now (web search already has a key)."""
    if payload["target"] != "brave_search":
        return None
    rows = await session.scalars(
        select(IntegrationRow).where(IntegrationRow.owner_id == owner_id).limit(500)
    )
    if any(
        row.payload.get("type") == "brave_search"
        and row.payload.get("enabled")
        and row.payload.get("secret_id")
        for row in rows
    ):
        return "credential_already_configured"
    return None


async def card_facts(
    session: AsyncSession, row: OwnerActionRow, facts: dict[str, Any]
) -> dict[str, Any]:
    payload = row.payload
    facts["credential"] = {"target": payload["target"], "service": payload.get("service")}
    return facts


async def connected_result(
    session: AsyncSession, owner_id: str, payload: dict[str, Any], resource: str, resource_id: str
) -> dict[str, Any]:
    """The owner's form created this resource: check it is the card's kind of
    connection and is configured. Only its kind and saved name are kept, never a value."""
    target = payload["target"]
    if TARGET_RESOURCE[target] != resource:
        raise LonoraError("owner_action_connection_mismatch", 422)
    if resource == "mcp":
        connection = await _connection(session, owner_id, resource_id)
        if connection is None:
            raise LonoraError("mcp_not_found", 404)
        if connection.payload.get("transport") != "http" or current_endpoint(connection) is None:
            raise LonoraError("owner_action_connection_mismatch", 422)
        return {"target": target, "connection_id": connection.id, "configured": True}
    if resource == "broker":
        account = await session.get(BrokerSessionRow, resource_id)
        if account is None or account.owner_id != owner_id:
            raise LonoraError("broker_connection_not_found", 404)
        return {"target": target, "configured": True}
    integration = await session.get(IntegrationRow, resource_id)
    if integration is None or integration.owner_id != owner_id:
        raise LonoraError("integrations_not_found", 404)
    config = integration.payload
    if config.get("type") != target or (
        not config.get("secret_id") if target == "brave_search" else not config.get("url")
    ):
        raise LonoraError("owner_action_connection_mismatch", 422)
    return {"target": target, "integration_id": integration.id, "configured": True}
