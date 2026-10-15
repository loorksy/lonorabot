"""Bind management approval to the actual broker state the owner reviewed."""

import sqlalchemy as sa
from alembic import op

revision = "0020_approval_broker_snapshot"
down_revision = "0019_collaboration_mentions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ln_trade_approvals",
        sa.Column("broker_snapshot", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("ln_trade_approvals", "broker_snapshot")
