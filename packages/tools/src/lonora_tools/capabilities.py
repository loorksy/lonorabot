"""What every agent can use right now: one report for the owner's Capabilities view and
for agents (``capabilities_list``).

It lists the trusted sources, the Skills agents installed or wrote (with where they came
from and whether the owner undid that version), the saved MCP servers and whether their
tools are trusted (and which need the write tier), the integrations and
feeds, and the built-in capabilities with their honest state: ``ready``,
``not_connected`` (the owner can connect it with one card) or ``not_set_up`` (this server
lacks the service: a workspace host, a browser, a search service). Presentation only:
every tool still checks its own boundary when it runs.
"""

from dataclasses import dataclass
from typing import Any, cast
from urllib.parse import urlsplit

from lonora_contracts.domain import Contract
from lonora_contracts.mcp import McpToolDeclaration
from lonora_db.client import Database
from lonora_db.schema import (
    AgentRow,
    IntegrationRow,
    McpConnectionRow,
    SkillRow,
    ThreadRow,
    TrustedSourceRow,
)
from lonora_db.skill_controls import read_skill_controls
from lonora_db.trusted_sources import (
    declared_connections,
    ensure_defaults,
    list_sources,
    source_data,
    source_names,
    write_tools,
)
from sqlalchemy import select

from .base import Tool
from .context import ToolContext

# Manifest source -> where the Skill came from (lonora_agent.skills.provenance).
PROVENANCE = {
    "builtin": "bundled",
    "owner": "owner",
    "legacy": "owner",
    "installed": "agent_authored",
    "external": "external",
}


@dataclass(frozen=True)
class Infrastructure:
    """What this server runs (deployment settings, never owner or model input)."""

    searxng: bool
    browser: bool
    workspace_host: bool
    chart_renderer: bool
    mcp_declarations: tuple[McpToolDeclaration, ...]
    mcp_owner_trust: bool


def built_in(
    infrastructure: Infrastructure,
    integrations: list[IntegrationRow],
    trusted_servers: int,
    owner_id: str,
) -> list[dict[str, Any]]:
    enabled = [row.payload for row in integrations if row.payload.get("enabled")]
    brave = any(item.get("type") == "brave_search" and item.get("secret_id") for item in enabled)
    calendar = any(item.get("type") == "economic_calendar" and item.get("url") for item in enabled)
    feeds = sum(1 for item in enabled if item.get("type") == "news_feed" and item.get("url"))
    declared = sum(1 for item in infrastructure.mcp_declarations if item.owner_id == owner_id)

    def entry(name: str, state: str, via: str | None = None) -> dict[str, Any]:
        return {"capability": name, "state": state, "via": via}

    return [
        entry(
            "web_search",
            "ready" if infrastructure.searxng or brave else "not_connected",
            "searxng" if infrastructure.searxng else "brave" if brave else None,
        ),
        entry("web_fetch", "ready"),
        entry("web_browse", "ready" if infrastructure.browser else "not_set_up"),
        entry("news_feeds", "ready", "subscribed" if feeds else "public_urls"),
        entry("economic_calendar", "ready" if calendar else "not_connected"),
        entry("workspace_files", "ready"),
        entry("workspace_execution", "ready" if infrastructure.workspace_host else "not_set_up"),
        entry("chart_images", "ready" if infrastructure.chart_renderer else "not_set_up"),
        entry(
            "mcp_tools",
            "ready"
            if declared or (infrastructure.mcp_owner_trust and trusted_servers)
            else "not_connected",
            "owner_trust" if infrastructure.mcp_owner_trust else "operator_only",
        ),
    ]


async def capability_report(
    db: Database, owner_id: str, infrastructure: Infrastructure, *, for_agent: bool
) -> dict[str, Any]:
    async with db.sessions() as session, session.begin():
        await ensure_defaults(session, owner_id)
        sources = await list_sources(session, owner_id)
        agent_names, connection_names = await source_names(session, owner_id, sources)
        agents = {
            row.id: row.name
            for row in await session.scalars(select(AgentRow).where(AgentRow.owner_id == owner_id))
        }
        skills = list(
            await session.scalars(
                select(SkillRow)
                .where(SkillRow.owner_id == owner_id)
                .order_by(SkillRow.updated_at.desc(), SkillRow.id)
                .limit(200)
            )
        )
        # The versions the owner undid, per agent: such a Skill no longer loads.
        revoked: set[tuple[str, str, str]] = set()
        for agent_id in sorted({row.agent_id for row in skills if row.agent_id in agents}):
            controls = await read_skill_controls(session, owner_id, agent_id)
            revoked |= {(agent_id, item.skill_id, item.version) for item in controls.revoked}
        servers = list(
            await session.scalars(
                select(McpConnectionRow)
                .where(McpConnectionRow.owner_id == owner_id)
                .order_by(McpConnectionRow.created_at, McpConnectionRow.id)
                .limit(100)
            )
        )
        integrations = list(
            await session.scalars(
                select(IntegrationRow)
                .where(IntegrationRow.owner_id == owner_id)
                .order_by(IntegrationRow.created_at, IntegrationRow.id)
                .limit(200)
            )
        )
        threads = {
            row.id: row.agent_id
            for row in await session.scalars(
                select(ThreadRow).where(
                    ThreadRow.owner_id == owner_id,
                    ThreadRow.id.in_(
                        sorted(
                            {
                                str(row.payload["thread_id"])
                                for row in integrations
                                if row.payload.get("thread_id")
                            }
                        )
                    ),
                )
            )
        }
    saved = {row.id for row in servers}
    # The owner's own trust of a server still saved; an operator entry stands for its
    # declaration, shown as such.
    trusted = {
        row.identifier: row
        for row in sources
        if row.kind == "mcp_server"
        and row.revoked_at is None
        and row.added_via != "operator"
        and row.identifier in saved
        and infrastructure.mcp_owner_trust
    }
    declared = declared_connections(infrastructure.mcp_declarations, owner_id)
    listed_sources = [source_data(row, agent_names, connection_names, declared) for row in sources]
    if for_agent:
        listed_sources = [
            {key: value for key, value in item.items() if key not in {"id", "added_by_agent_name"}}
            for item in listed_sources
            if item["active"]
        ]
    report: dict[str, Any] = {
        "trusted_sources": listed_sources,
        "skills": [skill_entry(row, agents, revoked) for row in skills],
        "mcp_servers": [
            server_entry(row, trusted.get(row.id), infrastructure, owner_id, for_agent=for_agent)
            for row in servers
        ],
        "integrations": [integration_entry(row, threads, agents) for row in integrations],
        "built_in": built_in(infrastructure, integrations, len(trusted), owner_id),
        "authority": "presentation_only; no capability carries money authority",
    }
    return report


def server_entry(
    row: McpConnectionRow,
    trust: TrustedSourceRow | None,
    infrastructure: Infrastructure,
    owner_id: str,
    *,
    for_agent: bool,
) -> dict[str, Any]:
    return {
        "connection_id": row.id,
        "name": row.payload.get("name"),
        "enabled": bool(row.payload.get("enabled")),
        "credentials_configured": bool(row.payload.get("secret_id")),
        "trusted_tier": trust.effect_tier if trust else None,
        "trusted_tools": sorted(trust.tool_hashes) if trust else [],
        "write_tools": write_tools(trust) if trust else [],
        "blocked_tools": list(trust.blocked_tools) if trust else [],
        "operator_declared": sum(
            1
            for item in infrastructure.mcp_declarations
            if item.owner_id == owner_id and item.connection_id == row.id
        ),
        "trust_source_id": trust.id if trust and not for_agent else None,
        "last_used_at": trust.last_used_at.isoformat() if trust and trust.last_used_at else None,
    }


def skill_entry(
    row: SkillRow, agents: dict[str, str], revoked: set[tuple[str, str, str]]
) -> dict[str, Any]:
    manifest: dict[str, Any] = row.payload.get("manifest") or {}
    source = str(manifest.get("source") or "legacy")
    package: dict[str, Any] = row.state.get("package") or {}
    versions: list[Any] = package.get("versions") or []
    last: Any = versions[-1] if versions else None
    latest = cast(dict[str, Any], last) if isinstance(last, dict) else {}
    repository = latest.get("repository_url")
    provenance = PROVENANCE.get(source, "unverified")
    # Undo denies this exact version (the Skill's manifest id, as loading checks it).
    skill_id = str(manifest.get("id") or row.payload.get("name") or "")
    version = manifest.get("version")
    undone = (row.agent_id or "", skill_id, str(version)) in revoked
    return {
        "resource_id": row.id,
        "agent_id": row.agent_id,
        "agent_name": agents.get(row.agent_id or ""),
        "skill_id": skill_id,
        "version": version,
        "provenance": provenance,
        "repository": urlsplit(repository).path.strip("/") if isinstance(repository, str) else None,
        "commit": latest.get("commit"),
        "enabled": bool(row.payload.get("enabled")),
        "undone": undone,
        "can_undo": bool(
            provenance in {"external", "agent_authored"}
            and row.agent_id in agents
            and version
            and not undone
        ),
        "installed_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


def integration_entry(
    row: IntegrationRow, threads: dict[str, str | None], agents: dict[str, str]
) -> dict[str, Any]:
    config = row.payload
    kind = str(config.get("type"))
    url = config.get("url")
    deliver = threads.get(str(config.get("thread_id") or ""))
    return {
        "id": row.id,
        "type": kind,
        "name": config.get("name"),
        "enabled": bool(config.get("enabled")),
        "configured": bool(config.get("secret_id"))
        if kind in {"brave_search", "telegram", "webhook"}
        else bool(url),
        # A feed's domain only: its URL may carry a token.
        "domain": urlsplit(str(url)).hostname
        if url and kind in {"news_feed", "economic_calendar"}
        else None,
        "deliver_to_agent_name": agents.get(deliver or "") if deliver else None,
    }


def infrastructure_of(context: ToolContext) -> Infrastructure:
    executor = getattr(context.workspace_access, "execution_configured", False)
    return Infrastructure(
        searxng=bool(context.searxng_url),
        browser=bool(context.browser_url),
        workspace_host=bool(executor),
        chart_renderer=context.chart_visual is not None,
        mcp_declarations=context.mcp_declarations,
        mcp_owner_trust=context.mcp_owner_trust,
    )


class CapabilitiesInput(Contract):
    pass


async def listing(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    report = await capability_report(
        context.db, context.owner_id, infrastructure_of(context), for_agent=True
    )
    return {
        **report,
        "guidance": "Use any ready capability without asking. not_connected: offer one "
        "connect_credential card. not_set_up: this server lacks it; say so plainly. A "
        "source outside trusted_sources needs one trust_source card.",
    }


def tools() -> list[Tool]:
    return [
        Tool(
            "capabilities_list",
            "List what every agent can use now: trusted sources, installed Skills and their "
            "origin, MCP servers and their trusted tools, integrations and news feeds, and "
            "built-in capabilities marked ready, not_connected (one owner card) or "
            "not_set_up on this server. Use it to answer what you can do or to choose a "
            "source; it grants nothing.",
            CapabilitiesInput,
            listing,
            read_only=True,
        ),
    ]
