"""The owner's workspace: when each agent's analytical-workspace files were copied into its
home in the persistent workspace (mandate 7.1, 14.1: survivors move before the old path
is deleted)."""

import sqlalchemy as sa
from alembic import op

revision = "0137_workspace_snapshot_moved"
down_revision = "0086_end_trading_restrictions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ln_analytical_workspaces",
        sa.Column("moved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column(
        "ln_analytical_workspaces",
        sa.Column("move_tried_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ln_analytical_workspaces", "move_tried_at")
    op.drop_column("ln_analytical_workspaces", "moved_at")
