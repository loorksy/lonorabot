"""Bounded Agent filesystem snapshots and fenced analytical operation receipts."""

import sqlalchemy as sa
from alembic import op

revision = "0028_analytical_workspace"
down_revision = "0027_device_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_analytical_workspaces",
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("revision", sa.Integer(), nullable=False),
        sa.Column("snapshot", sa.LargeBinary(), nullable=False),
        sa.Column("active_operation_id", sa.String(36)),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("revision >= 0", name="ln_workspace_revision"),
    )
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


def downgrade() -> None:
    op.drop_table("ln_workspace_operations")
    op.drop_table("ln_analytical_workspaces")
