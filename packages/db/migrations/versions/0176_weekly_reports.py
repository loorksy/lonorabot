"""The weekly report state on the morning brief record (VISION 5.5.6).

``weekly`` holds the latest weekly close the agents were woken for, each agent's report
run, and whether a morning brief has carried the reports. New nullable column only.
"""

import sqlalchemy as sa
from alembic import op

revision = "0176_weekly_reports"
down_revision = "0175_morning_briefs"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ln_morning_briefs", sa.Column("weekly", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("ln_morning_briefs", "weekly")
