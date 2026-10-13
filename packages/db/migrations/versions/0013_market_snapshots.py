"""Durable broker market observations; no credentials or synthetic prices."""

import sqlalchemy as sa
from alembic import op

revision = "0013_market_snapshots"
down_revision = "0012_reconciliation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_market_snapshots",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "connection_id",
            sa.String(36),
            sa.ForeignKey("ln_broker_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("symbol", sa.String(80), nullable=False),
        sa.Column("timeframe", sa.String(12), nullable=False),
        sa.Column("connection_version", sa.Integer(), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "owner_id", "connection_id", "symbol", "timeframe", name="market_snapshot_identity"
        ),
    )
    op.create_index("ix_ln_market_snapshots_owner_id", "ln_market_snapshots", ["owner_id"])


def downgrade() -> None:
    op.drop_table("ln_market_snapshots")
