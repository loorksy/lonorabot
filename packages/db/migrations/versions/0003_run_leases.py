"""0003 run leases schema revision."""

import sqlalchemy as sa
from alembic import op

revision = "0003_run_leases"
down_revision = "0002_thread_sequences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_steering",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("run_id", sa.String(length=36), nullable=False),
        sa.Column("message_id", sa.String(length=36), nullable=False),
        sa.Column("consumed", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["message_id"], ["ln_messages.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["run_id"], ["ln_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
    )
    op.create_index(op.f("ix_ln_steering_run_id"), "ln_steering", ["run_id"], unique=False)
    op.create_table(
        "ln_gateways",
        sa.Column("id", sa.String(length=120), nullable=False),
        sa.Column("state", sa.String(length=24), nullable=False),
        sa.Column("heartbeat_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_table(
        "ln_effect_receipts",
        sa.Column("key", sa.String(length=160), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("key"),
    )


def downgrade() -> None:
    op.drop_table("ln_effect_receipts")
    op.drop_table("ln_gateways")
    op.drop_table("ln_steering")
