"""Separate virtual execution from live journal entries and persist virtual positions."""

import sqlalchemy as sa
from alembic import op

revision = "0025_shadow_execution"
down_revision = "0024_trading_opportunity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("ln_agents", "ln_trading_journal"):
        op.add_column(
            table, sa.Column("execution_mode", sa.String(12), nullable=False, server_default="live")
        )
        op.create_check_constraint(
            table + "_execution_mode", table, "execution_mode IN ('live','shadow')"
        )
    op.create_index(
        "ix_ln_trading_journal_execution_mode", "ln_trading_journal", ["execution_mode"]
    )
    op.create_table(
        "ln_shadow_trades",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("ln_agents.id", ondelete="CASCADE")),
        sa.Column("thread_id", sa.String(36), sa.ForeignKey("ln_threads.id", ondelete="CASCADE")),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("account_id", sa.String(120), nullable=False),
        sa.Column("symbol", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("decision_id", sa.String(36)),
        sa.Column("thesis_id", sa.String(36)),
    )
    for column in ("owner_id", "account_id", "symbol", "status"):
        op.create_index("ix_ln_shadow_trades_" + column, "ln_shadow_trades", [column])


def downgrade() -> None:
    op.drop_table("ln_shadow_trades")
    for table in ("ln_trading_journal", "ln_agents"):
        op.drop_constraint(table + "_execution_mode", table, type_="check")
        op.drop_column(table, "execution_mode")
