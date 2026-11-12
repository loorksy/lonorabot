"""Trade Approval validity: the agent's reason and tolerance.

They are stored beside the request, never inside it (mandate 14.3.9): a Trade Approval
row gains ``reason`` and ``validity`` (the tolerance and the reference price
the server read when the card was made), and a journal row gains ``annotation``. The
stored requests, their fingerprints and operation ids are untouched, so an unresolved
journal row reconciles after this migration exactly as before. Existing approval rows
keep their stored expiry; new rows have none (10.3.1.3). The downgrade drops the columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "0061_trade_approval_validity"
down_revision = "0060_agent_trading_mode"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ln_trade_approvals",
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
    )
    op.add_column(
        "ln_trade_approvals",
        sa.Column("validity", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.add_column("ln_trading_journal", sa.Column("annotation", sa.JSON()))


def downgrade() -> None:
    op.drop_column("ln_trading_journal", "annotation")
    op.drop_column("ln_trade_approvals", "validity")
    op.drop_column("ln_trade_approvals", "reason")
