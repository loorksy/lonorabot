"""What is running in the owner's workspace (mandate 7.1.5): the supervisor's last listing,
written by the Gateway, and the owner's stop requests, carried out by the Gateway."""

import sqlalchemy as sa
from alembic import op

revision = "0139_workspace_running"
down_revision = "0136_workspace_processes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_workspace_running",
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("processes", sa.JSON(), nullable=False),
        sa.Column("listed_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ln_workspace_stops",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("pid", sa.Integer(), nullable=True),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("(pid IS NULL) = (agent_id IS NULL)", name="ln_workspace_stop_target"),
    )
    op.create_index("ix_ln_workspace_stops_owner_id", "ln_workspace_stops", ["owner_id"])
    op.create_index("ix_ln_workspace_stops_done_at", "ln_workspace_stops", ["done_at"])


def downgrade() -> None:
    op.drop_table("ln_workspace_stops")
    op.drop_table("ln_workspace_running")
