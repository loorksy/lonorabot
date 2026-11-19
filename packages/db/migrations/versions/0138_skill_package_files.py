"""Skill packages keep their files in their own store (map Q15): the package files kept so
far in each agent's analytical-workspace snapshot (skills/<id>/<version>/...) are copied
into it, before the old workspace is deleted (14.1)."""

import base64
import json

import sqlalchemy as sa
from alembic import op

revision = "0138_skill_package_files"
down_revision = "0137_workspace_snapshot_moved"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_skill_package_files",
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("path", sa.String(512), primary_key=True),
        sa.Column("content", sa.LargeBinary(), nullable=False),
        sa.Column("stored_at", sa.DateTime(timezone=True), nullable=False),
    )
    bind = op.get_bind()
    files = sa.table(
        "ln_skill_package_files",
        sa.column("agent_id", sa.String),
        sa.column("path", sa.String),
        sa.column("content", sa.LargeBinary),
        sa.column("stored_at", sa.DateTime(timezone=True)),
    )
    rows = bind.execute(
        sa.text("SELECT agent_id, snapshot, updated_at FROM ln_analytical_workspaces")
    ).all()
    for agent_id, snapshot, updated_at in rows:
        entries = json.loads(bytes(snapshot) or b"{}")
        copied = [
            {
                "agent_id": agent_id,
                "path": path,
                "content": base64.b64decode(body),
                "stored_at": updated_at,
            }
            for path, body in entries.items()
            if path.startswith("skills/")
        ]
        if copied:
            bind.execute(files.insert(), copied)


def downgrade() -> None:
    # The snapshots are left as they were, so packages created after this revision lose
    # their files: their versions then fail admission with skill_package_source_changed.
    op.drop_table("ln_skill_package_files")
