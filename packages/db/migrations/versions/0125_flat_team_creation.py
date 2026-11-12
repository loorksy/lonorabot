"""Lonora creates agents on its own judgment, with no card (mandate 3.1.2, 10.3).

Owner action cards of the removed ``create_agent`` (an agent's creation proposal) and
``agent_created`` (the Undo notice after a creation) kinds are deleted (14.3.9): the
server no longer reads, decides or renders those kinds, and neither card acted on money.
A pending proposal ends with its card; the agents those cards created stay. Only the
five fixed cards of 10.3 remain for the owner.

The downgrade restores nothing: the deleted cards are not recreated.
"""

import sqlalchemy as sa
from alembic import op

revision = "0125_flat_team_creation"
down_revision = ("0176_weekly_reports", "0061_trade_approval_validity")
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(
        sa.text("DELETE FROM ln_owner_actions WHERE kind IN ('create_agent', 'agent_created')")
    )


def downgrade() -> None:
    pass
