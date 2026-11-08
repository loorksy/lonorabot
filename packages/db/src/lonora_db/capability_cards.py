"""Trust and credential cards: the two ways capabilities reach the owner in chat.

``trust_source`` asks the owner to add one source to the trusted list: a GitHub owner or
repository a Skill comes from, a news feed's domain (with the feed to subscribe), or an
MCP server with the exact tools it advertised (each input schema pinned; tools that can
trade or move money are listed as blocked and never trusted). The card shows which
tools only read (the server marks them read-only) and which may change something; when
some may, the owner chooses the tier: read only (just the reading tools run) or also
non-financial writes.

``connect_credential`` offers a secure form in the conversation. The client posts the
value straight to the owner API (``/integrations/secrets``, ``/integrations``, ``/mcp``
or ``/trading/connections``); the card only learns which resource was connected. No
value ever reaches the card, the transcript, an event or an agent: agents see
"configured".

Everything a card shows is read here from records (the connection's saved name, the
pinned tool names that passed the name rules), never model prose.
"""

from typing import Any

from lonora_core.user_error import LonoraError
from lonora_security.network import endpoint_sha256
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import (
    BrokerSessionRow,
    IntegrationRow,
    McpConnectionRow,
    OwnerActionRow,
    TrustedSourceRow,
)
from .trusted_sources import feed_trusted, github_trusted, mcp_trust

TRUST_KINDS = ("mcp_server", "github_owner", "github_repo", "feed_domain")
CREDENTIAL_TARGETS = ("mcp_server", "news_feed", "brave_search", "economic_calendar", "broker")
# What each target's form creates, and the resource the decision names.
TARGET_RESOURCE = {
    "mcp_server": "mcp",
    "news_feed": "integration",
    "brave_search": "integration",
    "economic_calendar": "integration",
    "broker": "broker",
}


def trust_subject(kind: str, identifier: str) -> str:
    return "trusted-source:" + kind + ":" + identifier


def mcp_review_payload(
    connection_id: str,
    endpoint: str,
    tools: dict[str, str],
    blocked: list[str],
    read_only: list[str],
) -> dict[str, Any]:
    return {
        "source_kind": "mcp_server",
        "identifier": connection_id,
        "endpoint_sha256": endpoint,
        "tools": dict(sorted(tools.items())),
        "read_only": sorted(set(read_only) & set(tools)),
        "blocked": sorted(set(blocked)),
    }


def same_review(trusted: TrustedSourceRow, payload: dict[str, Any]) -> bool:
    """The server offers exactly what the owner already reviewed."""
    return (
        trusted.endpoint_sha256 == payload["endpoint_sha256"]
        and trusted.tool_hashes == payload["tools"]
        and sorted(trusted.read_only_tools) == payload.get("read_only", [])
        and sorted(trusted.blocked_tools) == payload["blocked"]
    )


def review_writes(payload: dict[str, Any]) -> list[str]:
    """The card's tools that may change something (not marked read-only)."""
    return sorted(set(payload["tools"]) - set(payload.get("read_only", [])))


def source_payload(
    kind: str, identifier: str, subscribe: dict[str, str] | None = None
) -> dict[str, Any]:
    payload: dict[str, Any] = {"source_kind": kind, "identifier": identifier}
    if subscribe is not None:
        payload["subscribe"] = {"url": subscribe["url"], "name": subscribe["name"]}
    return payload


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


async def stale_reason(
    session: AsyncSession, owner_id: str, kind: str, payload: dict[str, Any]
) -> str | None:
    if kind == "connect_credential":
        # A form stays usable until the owner fills it: what it connects is checked then.
        return None
    source_kind, identifier = payload["source_kind"], str(payload["identifier"])
    if source_kind == "mcp_server":
        connection = await _connection(session, owner_id, identifier)
        if connection is None:
            return "mcp_connection_missing"
        if current_endpoint(connection) != payload["endpoint_sha256"]:
            return "mcp_connection_changed"
        if not payload["tools"]:
            return "mcp_nothing_to_trust"
        trusted = await mcp_trust(session, owner_id, identifier)
        if (
            trusted is not None
            and trusted.added_via != "operator"
            and same_review(trusted, payload)
            # Trusted for reading while some tools write: the card can still widen it,
            # unless the server offers a tool that can trade or move money (read only).
            and (
                trusted.effect_tier == "write_nonfinancial"
                or not review_writes(payload)
                or bool(payload.get("blocked"))
            )
        ):
            return "source_already_trusted"
        return None
    if source_kind in {"github_owner", "github_repo"}:
        owner, _, repository = identifier.partition("/")
        if source_kind == "github_repo" and await github_trusted(
            session, owner_id, owner, repository
        ):
            return "source_already_trusted"
        # No repository is named "/": only github.com or the owner itself can match.
        if source_kind == "github_owner" and await github_trusted(session, owner_id, owner, "/"):
            return "source_already_trusted"
        return None
    subscribe = payload.get("subscribe")
    if await feed_trusted(session, owner_id, identifier):
        if subscribe is None:
            return "source_already_trusted"
        from .integrations import subscribed_feed

        if await subscribed_feed(session, owner_id, subscribe["url"]) is not None:
            return "feed_already_subscribed"
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
    payload, owner_id = row.payload, row.owner_id
    if row.kind == "connect_credential":
        facts["credential"] = {"target": payload["target"], "service": payload.get("service")}
        return facts
    source_kind, identifier = payload["source_kind"], str(payload["identifier"])
    source: dict[str, Any] = {"kind": source_kind, "label": identifier, "subscribe": False}
    if source_kind == "mcp_server":
        connection = await _connection(session, owner_id, identifier)
        trusted = await mcp_trust(session, owner_id, identifier)
        owned = trusted if trusted is not None and trusted.added_via != "operator" else None
        # The owner's own saved name for the server; the tools are the reviewed names.
        # review: the server changed what the owner trusted (not a request to widen).
        source.update(
            label=str(connection.payload.get("name") or "") or None if connection else None,
            tools=sorted(payload["tools"]),
            writes=review_writes(payload),
            blocked=list(payload["blocked"]),
            review=owned is not None and not same_review(owned, payload),
            tier=owned.effect_tier if owned is not None else None,
        )
    elif source_kind == "feed_domain":
        source["subscribe"] = payload.get("subscribe") is not None
    facts["source"] = source
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
