"""A routine counts the occurrences it skipped while its earlier run was unfinished.

``ln_routines.skipped_occurrences`` holds the occurrences that came due while an earlier
run of the routine was still queued, leased or running; the next run carries the count in
its metadata and the routine starts again from zero. A new column with a default only; no
stored row changes.
"""

import sqlalchemy as sa
from alembic import op

revision = "0130_routine_skipped_occurrences"
down_revision = "0129_grant_cards_gone"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ln_routines",
        sa.Column("skipped_occurrences", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("ln_routines", "skipped_occurrences")
