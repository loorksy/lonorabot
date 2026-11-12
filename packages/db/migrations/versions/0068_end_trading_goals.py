"""Trading goals are removed (mandate 14.2.4); active goals end (mandate 14.3.18.6).

Every goal that has not ended is cancelled with the code ``goal_removed``. The goal and
goal-decision tables stay as history: a decision names the journal operation it sent,
and journal, receipt and settlement records are never deleted. Their operations are
reconciled by the trading journal like any other operation.

The downgrade does not reopen the cancelled goals.
"""

import sqlalchemy as sa
from alembic import op

revision = "0068_end_trading_goals"
down_revision = "0067_decouple_goal_wakes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE ln_trading_goals SET state = (state::jsonb"
            " || jsonb_build_object('status', 'cancelled', 'code', 'goal_removed'))::json,"
            " version = version + 1"
            " WHERE coalesce(state->>'status', '') NOT IN ('cancelled', 'completed')"
        )
    )


def downgrade() -> None:
    pass
