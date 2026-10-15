"""Queryable opportunity identity and thesis state; historical evidence stays shared."""

import sqlalchemy as sa
from alembic import op

revision = "0024_trading_opportunity"
down_revision = "0023_task_outcome_projection"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_trading_opportunities",
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
        sa.Column("timeframe", sa.String(12), nullable=False),
        sa.Column("setup_key", sa.String(120), nullable=False),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_validated_at", sa.DateTime(timezone=True)),
        sa.UniqueConstraint(
            "owner_id",
            "agent_id",
            "account_id",
            "symbol",
            "timeframe",
            "setup_key",
            name="ln_opportunity_identity",
        ),
        sa.CheckConstraint(
            "status IN ('forming','confirmed','degraded','invalidated','expired','acted_on','completed')",
            name="ln_opportunity_status",
        ),
    )
    for column in ("owner_id", "account_id", "status", "expires_at"):
        op.create_index(
            "ix_ln_trading_opportunities_" + column, "ln_trading_opportunities", [column]
        )


def downgrade() -> None:
    op.drop_table("ln_trading_opportunities")
