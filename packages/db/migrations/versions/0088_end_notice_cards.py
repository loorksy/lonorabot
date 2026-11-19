"""The notice cards are removed (mandate 10.3.2, 14.2.7, 14.3.9).

An agent's own change (a watch it extended, a stop loss it tightened) is no longer a
system card: the agent says what it changed in its own words. Every owner-action row of
the removed ``watch_changed`` and ``stop_tightened`` kinds is deleted, whatever its
status. No client renders these kinds any more, and only rows of these two kinds
reference them (an older ``watch_changed`` card superseded by a newer one).

The downgrade changes no data: the deleted cards are not restored.
"""

import sqlalchemy as sa
from alembic import op

revision = "0088_end_notice_cards"
down_revision = "0100_execution_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM ln_owner_actions WHERE kind IN ('watch_changed', 'stop_tightened')")
    )


def downgrade() -> None:
    pass
