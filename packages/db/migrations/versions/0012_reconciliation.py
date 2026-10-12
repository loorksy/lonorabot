"""0012 reconciliation schema revision."""

from alembic import op

revision = "0012_reconciliation"
down_revision = "0011_trading_journal"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ln_journal_reconcile_due", "ln_trading_journal", ["status", "submitted_at"])


def downgrade() -> None:
    op.drop_index("ln_journal_reconcile_due", table_name="ln_trading_journal")
