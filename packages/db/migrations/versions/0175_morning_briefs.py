"""The morning brief record: one row per owner (VISION 11.1).

It keeps the brief's local time (minutes after midnight in the owner's time zone), the
local date of the last brief, the balance and equity per account that brief saw, and the
brief Lonora is writing now. New table only; no stored payload changes.
"""

import sqlalchemy as sa
from alembic import op

revision = "0175_morning_briefs"
down_revision = "0068_end_trading_goals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_morning_briefs",
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("brief_minute", sa.Integer(), nullable=False, server_default="420"),
        sa.Column("planned_date", sa.String(length=10), nullable=True),
        sa.Column("last_local_date", sa.String(length=10), nullable=True),
        sa.Column("last_sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("baseline", sa.JSON(), nullable=False),
        sa.Column("pending", sa.JSON(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["ln_owners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("owner_id"),
    )


def downgrade() -> None:
    op.drop_table("ln_morning_briefs")
