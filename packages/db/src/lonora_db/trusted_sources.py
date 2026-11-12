"""The owner's trusted-sources list: one per owner, visible and removable in Capabilities.

Inside the list agents install pinned Skills (``github``, ``github_owner``,
``github_repo``), use the reviewed tools of an MCP server (``mcp_server``: endpoint and
each tool's input schema pinned; the read tier runs only the tools the server marked
read-only at review, the non-financial write tier runs them all) and subscribe to news
feeds (``feed_domain``) without asking; the owner sees each one in Capabilities with
Undo. An ``operator`` entry (copied from ``LONORA_MCP_DECLARATIONS``) shows the
operator's declaration and authorizes nothing by itself; the owner's review of it makes
it the owner's own trust. Outside it an agent adds a source only when the owner's typed
message the run answers names it (``owner_message``, no card; ``lonora_tools.source_trust``);
rows added from the owner's former trust card stay ``owner_card``. Only the owner's
session removes or restores a source. Every owner starts with ``github.com`` (every
public repository, trusted as Skill imports always were, now visible and removable). No
source carries money authority: a tool that can trade or move money is never pinned.
"""

from collections.abc import Iterable
from typing import Any, Literal

from lonora_contracts.domain import utcnow
from lonora_contracts.mcp import McpToolDeclaration
from lonora_contracts.trusted_sources import normalize_identifier
from lonora_core.user_error import LonoraError
from sqlalchemy import select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import AgentRow, McpConnectionRow, TrustedSourceRow

AddedVia = Literal["default", "operator", "owner_ui", "owner_card", "owner_message"]
RemovedVia = Literal["owner_ui", "owner_card"]
DEFAULT_GITHUB = "github.com"


async def lock_sources(session: AsyncSession, owner_id: str) -> None:
    """Serialize changes to one owner's list (the default row, one active entry each)."""
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "trusted-sources:" + owner_id},
        )


async def ensure_defaults(session: AsyncSession, owner_id: str) -> None:
    """``github.com`` for an owner that never had it (one created after the migration).
    A removed default stays removed: only a row that never existed is added."""
    known = await session.scalar(
        select(TrustedSourceRow.id)
        .where(TrustedSourceRow.owner_id == owner_id, TrustedSourceRow.kind == "github")
        .limit(1)
    )
    if known is not None:
        return
    await lock_sources(session, owner_id)
    known = await session.scalar(
        select(TrustedSourceRow.id)
        .where(TrustedSourceRow.owner_id == owner_id, TrustedSourceRow.kind == "github")
        .limit(1)
    )
    if known is None:
        now = utcnow()
        session.add(
            TrustedSourceRow(
                owner_id=owner_id,
                kind="github",
                identifier=DEFAULT_GITHUB,
                effect_tier="read",
                tool_hashes={},
                read_only_tools=[],
                blocked_tools=[],
                added_via="default",
                created_at=now,
                updated_at=now,
            )
        )
        await session.flush()


async def active_source(
    session: AsyncSession, owner_id: str, kind: str, identifier: str, *, lock: bool = False
) -> TrustedSourceRow | None:
    query = select(TrustedSourceRow).where(
        TrustedSourceRow.owner_id == owner_id,
        TrustedSourceRow.kind == kind,
        TrustedSourceRow.identifier == identifier,
        TrustedSourceRow.revoked_at.is_(None),
    )
    return await session.scalar(query.with_for_update() if lock else query)


async def list_sources(session: AsyncSession, owner_id: str) -> list[TrustedSourceRow]:
    """Active entries first, then removed ones (the record, restorable), newest first."""
    rows = await session.scalars(
        select(TrustedSourceRow)
        .where(TrustedSourceRow.owner_id == owner_id)
        .order_by(TrustedSourceRow.created_at.desc(), TrustedSourceRow.id)
        .limit(500)
    )
    return sorted(rows, key=lambda row: row.revoked_at is not None)


def _changed(session: AsyncSession, row: TrustedSourceRow) -> None:
    emit(
        session,
        row.owner_id,
        "trusted_source.updated",
        payload={"id": row.id, "kind": row.kind, "active": row.revoked_at is None},
    )


async def trust_source(
    session: AsyncSession,
    owner_id: str,
    kind: str,
    identifier: str,
    *,
    via: AddedVia,
    tier: str = "read",
    agent_id: str | None = None,
    card_id: str | None = None,
    endpoint_sha256: str | None = None,
    tool_hashes: dict[str, str] | None = None,
    read_only_tools: list[str] | None = None,
    blocked_tools: list[str] | None = None,
) -> tuple[TrustedSourceRow, bool]:
    """Add a source, or (an MCP server reviewed again) replace its pinned review.

    Returns the active entry and whether this call changed the list. Callers are the
    owner's routes and the tools that act on the owner's own words in chat (checked there
    first, ``owner_message``); nothing else reaches this. The owner's
    review of an operator entry makes it the owner's own, even when nothing else changed.
    """
    try:
        identifier = normalize_identifier(kind, identifier)
    except ValueError as error:
        raise LonoraError(str(error), 422) from None
    if tier not in {"read", "write_nonfinancial"} or (kind != "mcp_server" and tier != "read"):
        raise LonoraError("trusted_source_tier_invalid", 422)
    if kind == "mcp_server":
        connection = await session.get(McpConnectionRow, identifier)
        if connection is None or connection.owner_id != owner_id:
            raise LonoraError("mcp_not_found", 404)
        if not endpoint_sha256 or not tool_hashes:
            raise LonoraError("mcp_nothing_to_trust", 422)
        if tier == "write_nonfinancial" and blocked_tools:
            # A server that offers a tool that can trade or move money is a trading server:
            # its other writes are not trusted either, only its reading tools run.
            raise LonoraError("trusted_source_write_blocked", 422)
    await lock_sources(session, owner_id)
    await ensure_defaults(session, owner_id)
    row = await active_source(session, owner_id, kind, identifier, lock=True)
    now = utcnow()
    pinned = dict(sorted((tool_hashes or {}).items()))
    # Only pinned tools can be read-only; anything else is treated as a write.
    read_only = sorted(set(read_only_tools or []) & set(pinned))
    blocked = sorted(set(blocked_tools or []))
    review: dict[str, Any] = {
        "effect_tier": tier,
        "endpoint_sha256": endpoint_sha256,
        "tool_hashes": pinned,
        "read_only_tools": read_only,
        "blocked_tools": blocked,
    }
    if row is not None:
        current = {
            "effect_tier": row.effect_tier,
            "endpoint_sha256": row.endpoint_sha256,
            "tool_hashes": row.tool_hashes,
            "read_only_tools": row.read_only_tools,
            "blocked_tools": row.blocked_tools,
        }
        if current == review and (row.added_via != "operator" or via == "operator"):
            return row, False
        row.effect_tier = tier
        row.endpoint_sha256 = endpoint_sha256
        row.tool_hashes, row.read_only_tools, row.blocked_tools = pinned, read_only, blocked
        row.added_via, row.added_by_agent_id, row.card_id = via, agent_id, card_id
        row.updated_at = now
        await session.flush()
        _changed(session, row)
        return row, True
    row = TrustedSourceRow(
        owner_id=owner_id,
        kind=kind,
        identifier=identifier,
        added_via=via,
        added_by_agent_id=agent_id,
        card_id=card_id,
        created_at=now,
        updated_at=now,
        **review,
    )
    session.add(row)
    await session.flush()
    _changed(session, row)
    return row, True


async def owned_source(
    session: AsyncSession, owner_id: str, source_id: str, *, lock: bool = False
) -> TrustedSourceRow:
    row = await session.get(
        TrustedSourceRow, source_id, with_for_update=lock, populate_existing=lock
    )
    if row is None or row.owner_id != owner_id:
        raise LonoraError("trusted_source_not_found", 404)
    return row


async def revoke_source(
    session: AsyncSession, owner_id: str, source_id: str, *, via: RemovedVia
) -> TrustedSourceRow:
    """Remove a source: agents ask again before using it. Idempotent; the row stays."""
    await lock_sources(session, owner_id)
    row = await owned_source(session, owner_id, source_id, lock=True)
    if row.revoked_at is None:
        row.revoked_at, row.revoked_via, row.updated_at = utcnow(), via, utcnow()
        await session.flush()
        _changed(session, row)
    return row


async def restore_source(session: AsyncSession, owner_id: str, source_id: str) -> TrustedSourceRow:
    """Put a removed source back exactly as it was reviewed; an MCP server whose tools
    changed since is blocked at use and asks for a new review."""
    await lock_sources(session, owner_id)
    row = await owned_source(session, owner_id, source_id, lock=True)
    if row.revoked_at is None:
        return row
    if await active_source(session, owner_id, row.kind, row.identifier) is not None:
        raise LonoraError("trusted_source_already_listed", 409)
    if row.kind == "mcp_server":
        connection = await session.get(McpConnectionRow, row.identifier)
        if connection is None or connection.owner_id != owner_id:
            raise LonoraError("mcp_not_found", 404)
    row.revoked_at, row.revoked_via, row.updated_at = None, None, utcnow()
    await session.flush()
    _changed(session, row)
    return row


async def revoke_server(session: AsyncSession, owner_id: str, connection_id: str) -> None:
    """The owner deleted a saved MCP server: its trust goes with it (the row stays as the
    record; it cannot be restored without the server)."""
    row = await active_source(session, owner_id, "mcp_server", connection_id)
    if row is not None:
        await revoke_source(session, owner_id, row.id, via="owner_ui")


async def revoke_feed_sites(
    session: AsyncSession, owner_id: str, host: str, remaining: list[str]
) -> list[str]:
    """The owner removed a feed: each trusted site that covers its host and no other feed
    still subscribed (``remaining`` hosts) leaves the list too, so an agent asks again
    before subscribing it. Removed sites stay restorable. Returns their domains."""
    try:
        domain = feed_domain_of(host)
    except ValueError:
        return []
    kept: set[str] = set()
    for item in remaining:
        try:
            kept.add(feed_domain_of(item))
        except ValueError:
            continue
    rows = await session.scalars(
        select(TrustedSourceRow).where(
            TrustedSourceRow.owner_id == owner_id,
            TrustedSourceRow.kind == "feed_domain",
            TrustedSourceRow.revoked_at.is_(None),
        )
    )

    def covers(site: str, value: str) -> bool:
        return value == site or value.endswith("." + site)

    removed: list[str] = []
    for row in list(rows):
        if covers(row.identifier, domain) and not any(covers(row.identifier, k) for k in kept):
            await revoke_source(session, owner_id, row.id, via="owner_ui")
            removed.append(row.identifier)
    return removed


async def github_trusted(session: AsyncSession, owner_id: str, owner: str, repository: str) -> bool:
    """Whether a public repository is inside the list: all of github.com, its owner or
    the repository itself. Call inside a transaction (the default may be added)."""
    await ensure_defaults(session, owner_id)
    owner, repository = owner.casefold(), repository.casefold().removesuffix(".git")
    wanted = {
        ("github", DEFAULT_GITHUB),
        ("github_owner", owner),
        ("github_repo", owner + "/" + repository),
    }
    rows = await session.scalars(
        select(TrustedSourceRow).where(
            TrustedSourceRow.owner_id == owner_id,
            TrustedSourceRow.kind.in_(["github", "github_owner", "github_repo"]),
            TrustedSourceRow.revoked_at.is_(None),
        )
    )
    return any((row.kind, row.identifier) in wanted for row in rows)


def feed_domain_of(host: str) -> str:
    """The domain a feed host is trusted under (``www.`` is the same site)."""
    return normalize_identifier("feed_domain", host)


async def feed_trusted(session: AsyncSession, owner_id: str, host: str) -> bool:
    """A feed host is trusted when it, or a parent domain, is in the list."""
    try:
        domain = feed_domain_of(host)
    except ValueError:
        return False
    rows = await session.scalars(
        select(TrustedSourceRow.identifier).where(
            TrustedSourceRow.owner_id == owner_id,
            TrustedSourceRow.kind == "feed_domain",
            TrustedSourceRow.revoked_at.is_(None),
        )
    )
    return any(domain == item or domain.endswith("." + item) for item in rows)


async def mcp_trust(
    session: AsyncSession, owner_id: str, connection_id: str
) -> TrustedSourceRow | None:
    return await active_source(session, owner_id, "mcp_server", connection_id)


async def mark_used(session: AsyncSession, source_id: str) -> None:
    row = await session.get(TrustedSourceRow, source_id, with_for_update=True)
    if row is not None:
        row.last_used_at = utcnow()


async def source_names(
    session: AsyncSession, owner_id: str, rows: list[TrustedSourceRow]
) -> tuple[dict[str, str], dict[str, str]]:
    """Agent names (who proposed it) and MCP connection names, read now."""
    agents = {row.added_by_agent_id for row in rows if row.added_by_agent_id}
    connections = {row.identifier for row in rows if row.kind == "mcp_server"}
    agent_names: dict[str, str] = {}
    connection_names: dict[str, str] = {}
    if agents:
        found = await session.scalars(
            select(AgentRow).where(AgentRow.owner_id == owner_id, AgentRow.id.in_(sorted(agents)))
        )
        agent_names = {agent.id: agent.name for agent in found}
    if connections:
        saved = await session.scalars(
            select(McpConnectionRow).where(
                McpConnectionRow.owner_id == owner_id, McpConnectionRow.id.in_(sorted(connections))
            )
        )
        connection_names = {item.id: str(item.payload.get("name") or "") for item in saved}
    return agent_names, connection_names


def declared_connections(
    declarations: Iterable[McpToolDeclaration], owner_id: str
) -> frozenset[str]:
    """The owner's connections the operator still declares tools on."""
    return frozenset(item.connection_id for item in declarations if item.owner_id == owner_id)


def write_tools(row: TrustedSourceRow) -> list[str]:
    """Pinned tools the server did not mark read-only: they run only at the write tier."""
    return sorted(set(row.tool_hashes) - set(row.read_only_tools))


def source_data(
    row: TrustedSourceRow,
    agent_names: dict[str, str],
    connection_names: dict[str, str],
    declared: frozenset[str] = frozenset(),
) -> dict[str, Any]:
    """One entry as the owner sees it: a plain label, never an internal id in the text.
    ``declared``: the connections the operator still declares; an operator entry without
    one waits for the owner's review (it authorizes nothing)."""
    label = (
        connection_names.get(row.identifier) or None if row.kind == "mcp_server" else row.identifier
    )
    server = row.kind == "mcp_server"
    return {
        "id": row.id,
        "kind": row.kind,
        "identifier": row.identifier,
        "label": label,
        "effect_tier": row.effect_tier,
        "tools": sorted(row.tool_hashes) if server else [],
        "write_tools": write_tools(row) if server else [],
        "blocked_tools": list(row.blocked_tools) if server else [],
        "needs_review": row.added_via == "operator" and row.identifier not in declared,
        "added_via": row.added_via,
        "added_by_agent_name": agent_names.get(row.added_by_agent_id or ""),
        "active": row.revoked_at is None,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
        "last_used_at": row.last_used_at.isoformat() if row.last_used_at else None,
        "revoked_at": row.revoked_at.isoformat() if row.revoked_at else None,
    }
