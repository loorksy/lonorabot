"""Persist validated native visual responses with their existing conversation message."""

import sqlalchemy as sa
from alembic import op

revision = "0032_message_rich_content"
down_revision = "0031_event_delivery_indexes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Nullable and without a server default: existing messages stay text-only;
    # PostgreSQL does not rewrite the historical conversation table.
    op.add_column("ln_messages", sa.Column("rich_content", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("ln_messages", "rich_content")
