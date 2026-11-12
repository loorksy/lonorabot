"""The owner-signals record (8.1): what the owner did, append-only.

Thread reads and position closes made outside Lonora, each with its time. Fresh
start: nothing is backfilled. The downgrade drops the record.
"""

import sqlalchemy as sa
from alembic import op

revision = "0130_owner_signals"
down_revision = "0050_genui_state_and_origin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_owner_signals",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("kind", sa.String(length=24), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("observed_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "kind IN ('thread_read','external_close')", name="ln_owner_signals_kind"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["ln_owners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_ln_owner_signals_owner_time", "ln_owner_signals", ["owner_id", "observed_at"]
    )


def downgrade() -> None:
    op.drop_index("ix_ln_owner_signals_owner_time", table_name="ln_owner_signals")
    op.drop_table("ln_owner_signals")
