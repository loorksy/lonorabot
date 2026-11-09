"""Trusted sources: where agents may install and use capabilities without asking.

Inside the owner's list an agent installs a pinned Skill, uses a reviewed MCP tool or
subscribes to a news feed silently, and the owner sees it in Capabilities with Undo.
Outside the list it raises one owner card. No source ever carries money authority.
"""

import re
from typing import Literal

from pydantic import Field, model_validator

from .domain import Contract

TrustedSourceKind = Literal["github", "github_owner", "github_repo", "mcp_server", "feed_domain"]
# What a trusted MCP server's tools may do: read only, or also write outside money (post a
# note, send a message). Nothing that can trade or move money is ever trusted.
EffectTier = Literal["read", "write_nonfinancial"]

GITHUB_OWNER = re.compile(r"^[a-z0-9][a-z0-9-]{0,38}$")
GITHUB_REPO = re.compile(r"^[a-z0-9][a-z0-9-]{0,38}/[a-z0-9_.-]{1,100}$")
HOSTNAME = re.compile(
    r"^(?=.{4,253}$)([a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z][a-z0-9-]{0,61}[a-z0-9]$"
)


def normalize_identifier(kind: str, identifier: str) -> str:
    """The canonical identifier of a source the owner or a card names; raises ValueError."""
    value = identifier.strip().casefold()
    if kind == "github":
        if value != "github.com":
            raise ValueError("trusted_source_identifier_invalid")
        return value
    if kind == "github_owner":
        if not GITHUB_OWNER.match(value):
            raise ValueError("trusted_source_identifier_invalid")
        return value
    if kind == "github_repo":
        value = value.removesuffix(".git")
        if not GITHUB_REPO.match(value) or value.split("/")[1] in {".", ".."}:
            raise ValueError("trusted_source_identifier_invalid")
        return value
    if kind == "feed_domain":
        value = value.rstrip(".").removeprefix("www.")
        if not HOSTNAME.match(value) or value.endswith((".localhost", ".local", ".internal")):
            raise ValueError("trusted_source_identifier_invalid")
        return value
    if kind == "mcp_server":
        if not 1 <= len(identifier) <= 80:
            raise ValueError("trusted_source_identifier_invalid")
        return identifier
    raise ValueError("trusted_source_kind_invalid")


class TrustedSourceCreate(Contract):
    """The owner adds a GitHub owner or repository, or a feed domain, to the list. An MCP
    server is trusted only after its tools were reviewed (``McpTrustRequest``)."""

    kind: Literal["github", "github_owner", "github_repo", "feed_domain"]
    identifier: str = Field(min_length=1, max_length=300)

    @model_validator(mode="after")
    def canonical(self) -> "TrustedSourceCreate":
        self.identifier = normalize_identifier(self.kind, self.identifier)
        return self


class McpTrustRequest(Contract):
    """The owner trusts the tools a preview showed: ``digest`` binds the exact list."""

    tier: EffectTier
    digest: str = Field(pattern=r"^[0-9a-f]{64}$")
