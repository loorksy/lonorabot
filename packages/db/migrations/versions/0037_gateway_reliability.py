"""Per-item failure records, run recovery counts and per-step gateway liveness."""

import sqlalchemy as sa
from alembic import op

revision = "0037_gateway_reliability"
down_revision = "0036_durable_records"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_item_failures",
        sa.Column("kind", sa.String(40), primary_key=True),
        sa.Column("item_id", sa.String(160), primary_key=True),
        sa.Column("owner_id", sa.String(36), sa.ForeignKey("ln_owners.id", ondelete="CASCADE")),
        sa.Column("failures", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("code", sa.String(120), nullable=False),
        sa.Column("first_failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_failed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("next_attempt_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("quarantined_at", sa.DateTime(timezone=True)),
    )
    op.create_index("ln_item_failure_due", "ln_item_failures", ["kind", "next_attempt_at"])
    op.add_column(
        "ln_runs",
        sa.Column("recovery_count", sa.Integer(), nullable=False, server_default="0"),
    )
    op.add_column(
        "ln_gateways",
        sa.Column("liveness", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("ln_gateways", "liveness")
    op.drop_column("ln_runs", "recovery_count")
    op.drop_index("ln_item_failure_due", table_name="ln_item_failures")
    op.drop_table("ln_item_failures")
