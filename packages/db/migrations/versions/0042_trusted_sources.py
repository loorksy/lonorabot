"""One trusted-sources list per owner, visible and removable in Capabilities.

The data step makes today's implicit trust visible: every owner gets ``github.com``
(every public repository, as Skill imports trusted it before) and one ``mcp_server``
entry per saved connection that the operator declared in ``LONORA_MCP_DECLARATIONS``
(read in this process's environment), with the declared endpoint and schema hashes
pinned at the read tier. Owners or connections that no longer exist are skipped, and a
source already listed is not added again, so running it again adds nothing. The
declarations themselves keep working as an optional operator override. The downgrade
drops the table.
"""

import json
import os
import re
import uuid
from datetime import UTC, datetime
from typing import Any, cast

import sqlalchemy as sa
from alembic import op

revision = "0042_trusted_sources"
down_revision = "0041_supervision_grants"
branch_labels = None
depends_on = None

HASH = re.compile(r"^[0-9a-f]{64}$")


def declared_servers(raw: str | None) -> dict[tuple[str, str], dict[str, Any]]:
    """Operator declarations grouped per owner and connection; invalid ones are skipped."""
    try:
        values: Any = json.loads(raw) if raw else []
    except ValueError:
        return {}
    servers: dict[tuple[str, str], dict[str, Any]] = {}
    for value in cast(list[Any], values) if isinstance(values, list) else []:
        if not isinstance(value, dict):
            continue
        item = cast(dict[str, Any], value)
        owner, connection = item.get("owner_id"), item.get("connection_id")
        endpoint, tool, schema = (
            item.get("endpoint_sha256"),
            item.get("tool_name"),
            item.get("input_schema_sha256"),
        )
        if (
            not isinstance(owner, str)
            or not isinstance(connection, str)
            or not isinstance(tool, str)
            or not isinstance(endpoint, str)
            or not isinstance(schema, str)
            or not HASH.match(endpoint)
            or not HASH.match(schema)
            or item.get("effect", "read_only") != "read_only"
            or item.get("credential_scope", "integration") != "integration"
        ):
            continue
        server = servers.setdefault((owner, connection), {"endpoint": endpoint, "tools": {}})
        if server["endpoint"] == endpoint:
            server["tools"][tool] = schema
    return servers


def _listed(connection: Any, owner_id: str, kind: str, identifier: str) -> bool:
    return (
        connection.execute(
            sa.text(
                "SELECT 1 FROM ln_trusted_sources WHERE owner_id = :owner AND kind = :kind "
                "AND identifier = :identifier AND revoked_at IS NULL"
            ),
            {"owner": owner_id, "kind": kind, "identifier": identifier},
        ).first()
        is not None
    )


def seed_sources(connection: Any, raw_declarations: str | None) -> int:
    now = datetime.now(UTC)
    added = 0
    owners = [row[0] for row in connection.execute(sa.text("SELECT id FROM ln_owners")).all()]
    for owner_id in owners:
        if not _listed(connection, owner_id, "github", "github.com"):
            connection.execute(
                sa.text(
                    "INSERT INTO ln_trusted_sources (id, owner_id, kind, identifier, effect_tier, "
                    "tool_hashes, blocked_tools, added_via, created_at, updated_at) VALUES "
                    "(:id, :owner, 'github', 'github.com', 'read', '{}', '[]', 'default', "
                    ":now, :now)"
                ),
                {"id": str(uuid.uuid4()), "owner": owner_id, "now": now},
            )
            added += 1
    for (owner_id, connection_id), server in sorted(declared_servers(raw_declarations).items()):
        saved = connection.execute(
            sa.text("SELECT 1 FROM ln_mcp_connections WHERE id = :id AND owner_id = :owner"),
            {"id": connection_id, "owner": owner_id},
        ).first()
        if saved is None or _listed(connection, owner_id, "mcp_server", connection_id):
            continue
        connection.execute(
            sa.text(
                "INSERT INTO ln_trusted_sources (id, owner_id, kind, identifier, effect_tier, "
                "endpoint_sha256, tool_hashes, blocked_tools, added_via, created_at, updated_at) "
                "VALUES (:id, :owner, 'mcp_server', :identifier, 'read', :endpoint, :tools, "
                "'[]', 'operator', :now, :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "owner": owner_id,
                "identifier": connection_id,
                "endpoint": server["endpoint"],
                "tools": json.dumps(server["tools"], sort_keys=True),
                "now": now,
            },
        )
        added += 1
    return added


def upgrade() -> None:
    op.create_table(
        "ln_trusted_sources",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("identifier", sa.String(300), nullable=False),
        sa.Column("effect_tier", sa.String(24), nullable=False),
        sa.Column("endpoint_sha256", sa.String(64)),
        sa.Column("tool_hashes", sa.JSON(), nullable=False),
        sa.Column("blocked_tools", sa.JSON(), nullable=False),
        sa.Column("added_via", sa.String(16), nullable=False),
        sa.Column("added_by_agent_id", sa.String(36)),
        sa.Column("card_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_via", sa.String(16)),
        sa.CheckConstraint(
            "kind IN ('github','github_owner','github_repo','mcp_server','feed_domain')",
            name="ln_trusted_source_kind",
        ),
        sa.CheckConstraint(
            "effect_tier IN ('read','write_nonfinancial')", name="ln_trusted_source_tier"
        ),
        sa.CheckConstraint(
            "added_via IN ('default','operator','owner_ui','owner_card')",
            name="ln_trusted_source_added_via",
        ),
        sa.CheckConstraint(
            "revoked_via IS NULL OR revoked_via IN ('owner_ui','owner_card')",
            name="ln_trusted_source_revoked_via",
        ),
    )
    op.create_index(
        "ln_trusted_source_owner_kind",
        "ln_trusted_sources",
        ["owner_id", "kind", "revoked_at"],
    )
    op.create_index(
        "ln_trusted_source_active",
        "ln_trusted_sources",
        ["owner_id", "kind", "identifier"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
    seed_sources(op.get_bind(), os.environ.get("LONORA_MCP_DECLARATIONS"))


def downgrade() -> None:
    op.drop_index("ln_trusted_source_active", table_name="ln_trusted_sources")
    op.drop_index("ln_trusted_source_owner_kind", table_name="ln_trusted_sources")
    op.drop_table("ln_trusted_sources")
