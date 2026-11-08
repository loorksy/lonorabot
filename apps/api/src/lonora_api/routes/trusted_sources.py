"""The owner's trusted-sources list: list, add, remove and restore; owner session only.

Inside the list agents install pinned Skills, use reviewed MCP tools and subscribe to
feeds without asking (``lonora_db.trusted_sources``). An MCP server is trusted only for
the tools the owner previewed: the preview lists them (tools that could trade or move
money are blocked and never trusted; the ones that may change something run only at the
write tier) with a digest, and trusting re-reads the server and refuses if anything
changed since the preview. No source carries money authority.
"""

from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_adapters.mcp.policy import ToolReview, endpoint_sha256, review_digest, review_tools
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.mcp import McpConnection
from lonora_contracts.trusted_sources import McpTrustRequest, TrustedSourceCreate
from lonora_core.user_error import LonoraError
from lonora_db.schema import McpConnectionRow
from lonora_db.trusted_sources import (
    declared_connections,
    ensure_defaults,
    list_sources,
    mcp_trust,
    restore_source,
    revoke_source,
    source_data,
    source_names,
    trust_source,
)
from lonora_tools.mcp import advertised_tools

from ..middleware.auth import require_owner, runtime
from ..runtime import ApiRuntime

router = APIRouter(prefix="/trusted-sources")


def declared(rt: ApiRuntime, owner_id: str) -> frozenset[str]:
    return declared_connections(rt.settings.mcp_declarations, owner_id)


async def listing(rt: ApiRuntime, owner_id: str) -> list[dict[str, Any]]:
    async with rt.db.sessions() as session, session.begin():
        await ensure_defaults(session, owner_id)
        rows = await list_sources(session, owner_id)
        agents, connections = await source_names(session, owner_id, rows)
        return [source_data(row, agents, connections, declared(rt, owner_id)) for row in rows]


@router.get("")
async def sources(request: Request, owner: OwnerIdentity = Depends(require_owner)) -> list[Any]:
    return await listing(runtime(request), owner.id)


@router.post("", status_code=201)
async def add(
    request: Request, body: TrustedSourceCreate, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        row, _ = await trust_source(session, owner.id, body.kind, body.identifier, via="owner_ui")
        agents, connections = await source_names(session, owner.id, [row])
        return source_data(row, agents, connections, declared(rt, owner.id))


@router.post("/{source_id}/revoke")
async def revoke(
    request: Request, source_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        row = await revoke_source(session, owner.id, source_id, via="owner_ui")
        agents, connections = await source_names(session, owner.id, [row])
        return source_data(row, agents, connections, declared(rt, owner.id))


@router.post("/{source_id}/restore")
async def restore(
    request: Request, source_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    rt = runtime(request)
    async with rt.db.sessions() as session, session.begin():
        row = await restore_source(session, owner.id, source_id)
        agents, connections = await source_names(session, owner.id, [row])
        return source_data(row, agents, connections, declared(rt, owner.id))


async def review(
    rt: ApiRuntime, owner_id: str, connection_id: str
) -> tuple[McpConnection, ToolReview, str]:
    """Read the server's tools now (network IO outside any transaction)."""
    if not rt.settings.mcp_owner_trust:
        raise LonoraError("mcp_owner_trust_disabled", 403)
    async with rt.db.sessions() as session:
        row = await session.get(McpConnectionRow, connection_id)
        if row is None or row.owner_id != owner_id:
            raise LonoraError("mcp_not_found", 404)
        config = McpConnection.model_validate(row.payload)
    if config.transport != "http" or not config.url:
        raise LonoraError("mcp_stdio_isolation_required", 403)
    reviewed = review_tools(await advertised_tools(rt.services(owner_id).secrets, config))
    digest = review_digest(
        endpoint_sha256(config.url), reviewed.tools, reviewed.blocked, reviewed.read_only
    )
    return config, reviewed, digest


@router.post("/mcp/{connection_id}/preview")
async def preview(
    request: Request, connection_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    rt = runtime(request)
    config, reviewed, digest = await review(rt, owner.id, connection_id)
    async with rt.db.sessions() as session:
        trusted = await mcp_trust(session, owner.id, connection_id)
    owned = trusted is not None and trusted.added_via != "operator"
    return {
        "name": config.name,
        "tools": sorted(reviewed.tools),
        "writes": reviewed.writes,
        "blocked": reviewed.blocked,
        "unsupported": reviewed.unsupported,
        "digest": digest,
        "trusted_tier": trusted.effect_tier if owned and trusted is not None else None,
    }


@router.post("/mcp/{connection_id}")
async def trust_mcp(
    request: Request,
    connection_id: str,
    body: McpTrustRequest,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    rt = runtime(request)
    config, reviewed, digest = await review(rt, owner.id, connection_id)
    if digest != body.digest:
        # The server changed what it offers after the preview: the owner reviews it again.
        raise LonoraError("mcp_tools_changed", 409)
    if not reviewed.tools:
        raise LonoraError("mcp_nothing_to_trust", 422)
    async with rt.db.sessions() as session, session.begin():
        row = await session.get(McpConnectionRow, connection_id, with_for_update=True)
        if (
            row is None
            or row.owner_id != owner.id
            or McpConnection.model_validate(row.payload) != config
        ):
            raise LonoraError("mcp_connection_changed", 409)
        trusted, _ = await trust_source(
            session,
            owner.id,
            "mcp_server",
            connection_id,
            via="owner_ui",
            tier=body.tier,
            endpoint_sha256=endpoint_sha256(config.url or ""),
            tool_hashes=reviewed.tools,
            read_only_tools=reviewed.read_only,
            blocked_tools=reviewed.blocked,
        )
        agents, connections = await source_names(session, owner.id, [trusted])
        return source_data(trusted, agents, connections, declared(rt, owner.id))
