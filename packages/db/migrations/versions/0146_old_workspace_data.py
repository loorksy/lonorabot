"""The former analytical workspace's stored data (W-WS step 5b; 14.1, 14.3.9):

- ``ln_workspace_operations`` (the old tools' receipts) is dropped: nothing reads it since
  the old tools were deleted.
- Stored skill manifests that still require a removed tool name the tool that replaced it
  (``workspace_read`` -> ``workspace_file_read``, ``workspace_update`` ->
  ``workspace_file_write``, ``workspace_inspect`` and ``workspace_execute`` ->
  ``workspace_run``), in the skill resources, their package versions and the saved
  versions. Package digests cover the files, never the manifest, so they still verify.
- Saved stdio MCP servers are deleted and every other saved server loses the ``transport``
  and ``command`` fields, before the contract drops them: the workspace runs a local MCP
  server as an agent's own process (#197). A stdio server was refused before any review, so
  none was ever trusted.

``ln_analytical_workspaces`` stays: the one-time mover still copies snapshots it has not
copied yet. The downgrade recreates the receipts table empty; the rewritten names and the
deleted stdio records are not restored."""

from typing import Any, cast

import sqlalchemy as sa
from alembic import op

revision = "0146_old_workspace_data"
down_revision = "0087_end_money_limits"
branch_labels = None
depends_on = None

REPLACED = {
    "workspace_read": "workspace_file_read",
    "workspace_update": "workspace_file_write",
    "workspace_inspect": "workspace_run",
    "workspace_execute": "workspace_run",
}


def renamed(value: Any) -> tuple[Any, bool]:
    """``value`` with every ``required_tools`` list rewritten; whether anything changed."""
    if isinstance(value, dict):
        changed, result = False, dict[str, Any]()
        for key, item in cast(dict[str, Any], value).items():
            if key == "required_tools" and isinstance(item, list):
                names = [str(name) for name in cast(list[Any], item)]
                tools = list(dict.fromkeys(REPLACED.get(name, name) for name in names))
                changed = changed or tools != names
                result[key] = tools
            else:
                result[key], moved = renamed(item)
                changed = changed or moved
        return result, changed
    if isinstance(value, list):
        items = [renamed(item) for item in cast(list[Any], value)]
        return [item for item, _ in items], any(moved for _, moved in items)
    return value, False


def rewrite(table: str, *columns: str) -> None:
    bind = op.get_bind()
    rows = sa.table(
        table, sa.column("id", sa.String()), *(sa.column(c, sa.JSON()) for c in columns)
    )
    for row in bind.execute(sa.select(rows)).mappings().all():
        values: dict[str, Any] = {}
        for column in columns:
            value, changed = renamed(row[column])
            if changed:
                values[column] = value
        if values:
            bind.execute(sa.update(rows).where(rows.c.id == row["id"]).values(**values))


def upgrade() -> None:
    op.drop_table("ln_workspace_operations")
    rewrite("ln_skills", "payload", "state")
    bind = op.get_bind()
    versions = sa.table(
        "ln_skill_versions",
        sa.column("skill_id", sa.String()),
        sa.column("version", sa.Integer()),
        sa.column("payload", sa.JSON()),
    )
    for row in bind.execute(sa.select(versions)).mappings().all():
        value, changed = renamed(row["payload"])
        if changed:
            bind.execute(
                sa.update(versions)
                .where(versions.c.skill_id == row["skill_id"], versions.c.version == row["version"])
                .values(payload=value)
            )
    servers = sa.table(
        "ln_mcp_connections", sa.column("id", sa.String()), sa.column("payload", sa.JSON())
    )
    for row in bind.execute(sa.select(servers)).mappings().all():
        payload = dict(row["payload"] or {})
        if payload.get("transport") == "stdio":
            bind.execute(sa.delete(servers).where(servers.c.id == row["id"]))
        elif "transport" in payload or "command" in payload:
            payload.pop("transport", None)
            payload.pop("command", None)
            bind.execute(
                sa.update(servers).where(servers.c.id == row["id"]).values(payload=payload)
            )


def downgrade() -> None:
    op.create_table(
        "ln_workspace_operations",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("ln_runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("lease_fence", sa.Integer(), nullable=False),
        sa.Column("request_hash", sa.String(64), nullable=False),
        sa.Column("base_revision", sa.Integer(), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('running','completed','failed','abandoned')",
            name="ln_workspace_operation_status",
        ),
    )
    op.create_index("ix_ln_workspace_operations_agent_id", "ln_workspace_operations", ["agent_id"])
    op.create_index("ix_ln_workspace_operations_run_id", "ln_workspace_operations", ["run_id"])
