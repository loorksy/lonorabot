"""App opens and the learned brief time (VISION 11.1, 8.1).

``ln_app_opens`` keeps the owner's first app open on each local date of the device, with
the device's time zone. ``ln_morning_briefs.planned_date`` is the local date the brief
time was last planned for, so it moves at most once per day. New table and a new
nullable column only; no stored payload changes.
"""

import sqlalchemy as sa
from alembic import op

revision = "0177_app_opens"
down_revision = "0138_skill_package_files"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_app_opens",
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("local_date", sa.String(length=10), nullable=False),
        sa.Column("opened_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("timezone", sa.String(length=64), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["ln_owners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("owner_id", "local_date"),
    )
    op.add_column("ln_morning_briefs", sa.Column("planned_date", sa.String(length=10)))


def downgrade() -> None:
    op.drop_column("ln_morning_briefs", "planned_date")
    op.drop_table("ln_app_opens")
