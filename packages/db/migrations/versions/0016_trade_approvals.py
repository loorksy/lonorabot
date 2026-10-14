"""Durable immutable financial proposals consumed by fenced workers."""

import sqlalchemy as sa
from alembic import op

revision = "0016_trade_approvals"
down_revision = "0015_trading_goals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_trade_approvals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "run_id", sa.String(36), sa.ForeignKey("ln_runs.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "thread_id",
            sa.String(36),
            sa.ForeignKey("ln_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("call_id", sa.String(120), nullable=False),
        sa.Column("requests", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("results", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    for field in ("owner_id", "run_id", "thread_id"):
        op.create_index("ix_ln_trade_approvals_" + field, "ln_trade_approvals", [field])


def downgrade() -> None:
    op.drop_table("ln_trade_approvals")
