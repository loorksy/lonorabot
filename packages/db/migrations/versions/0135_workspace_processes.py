"""The owner's workspace: background processes an agent started, kept until the agent has
been told they ended (mandate 7.1.2)."""

import sqlalchemy as sa
from alembic import op

revision = "0135_workspace_processes"
down_revision = "0070_secret_scopes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_workspace_processes",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("boot_id", sa.String(36), nullable=False),
        sa.Column("pid", sa.Integer(), nullable=False),
        sa.Column("command", sa.Text(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("exit_code", sa.Integer(), nullable=True),
        sa.Column("outcome", sa.String(16), nullable=True),
        sa.Column("reported_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reported_run_id", sa.String(36), nullable=True),
        sa.CheckConstraint(
            "outcome IS NULL OR outcome IN ('exited','stopped','restarted','lost')",
            name="ln_workspace_process_outcome",
        ),
    )
    op.create_index("ix_ln_workspace_processes_owner_id", "ln_workspace_processes", ["owner_id"])
    op.create_index("ix_ln_workspace_processes_agent_id", "ln_workspace_processes", ["agent_id"])


def downgrade() -> None:
    op.drop_table("ln_workspace_processes")
