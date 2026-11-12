"""Trust cards: how a source reaches the owner's trusted list from chat.

``trust_source`` asks the owner to add one source to the trusted list: a GitHub owner or
repository a Skill comes from, a news feed's domain (with the feed to subscribe), or an
MCP server with the exact tools it advertised (each input schema pinned; tools that can
trade or move money are listed as blocked and never trusted). The card shows which
tools only read (the server marks them read-only) and which may change something; when
some may, the owner chooses the tier: read only (just the reading tools run) or also
non-financial writes.

A credential reaches Lonora through the Secret card (``secret_cards``), never here.

Everything a card shows is read here from records (the connection's saved name, the
pinned tool names that passed the name rules), never model prose.
"""

from typing import Any

from lonora_core.user_error import LonoraError
from lonora_security.network import endpoint_sha256
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import (
    McpConnectionRow,
    OwnerActionRow,
    TrustedSourceRow,
)
from .trusted_sources import feed_trusted, github_trusted, mcp_trust

TRUST_KINDS = ("mcp_server", "github_owner", "github_repo", "feed_domain")


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


async def _connection(
    session: AsyncSession, owner_id: str, connection_id: str
) -> McpConnectionRow | None:
    row = await session.get(McpConnectionRow, connection_id)
    return row if row is not None and row.owner_id == owner_id else None


def current_endpoint(row: McpConnectionRow) -> str | None:
    if row.payload.get("url_secret_id"):
        # The address is in the encrypted store; the row keeps its fingerprint.
        return row.payload.get("endpoint_sha256")
    try:
        return endpoint_sha256(str(row.payload.get("url") or ""))
    except LonoraError:
        return None


async def stale_reason(
    session: AsyncSession, owner_id: str, kind: str, payload: dict[str, Any]
) -> str | None:
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


async def card_facts(
    session: AsyncSession, row: OwnerActionRow, facts: dict[str, Any]
) -> dict[str, Any]:
    payload, owner_id = row.payload, row.owner_id
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
