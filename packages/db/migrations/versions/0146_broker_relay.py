"""0146 the broker relay: MetaApi requests the API process hands to the Gateway.

Only the Gateway keeps a MetaApi connection, so each account has one subscription and one
synchronization owner. The API process writes a request row here and waits for the answer.
"""

import sqlalchemy as sa
from alembic import op

revision = "0146_broker_relay"
down_revision = "0200_old_workspace_data"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_broker_relay",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("connection_id", sa.String(36), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("arguments", sa.JSON(), nullable=False),
        sa.Column("state", sa.String(12), nullable=False),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("error_code", sa.String(120), nullable=True),
        sa.Column("error_status", sa.Integer(), nullable=True),
        sa.Column("error_details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "state IN ('pending', 'claimed', 'answered', 'cancelled')",
            name="broker_relay_state",
        ),
    )
    op.create_index(
        "ix_ln_broker_relay_pending",
        "ln_broker_relay",
        ["created_at"],
        postgresql_where=sa.text("state = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ix_ln_broker_relay_pending", table_name="ln_broker_relay")
    op.drop_table("ln_broker_relay")
