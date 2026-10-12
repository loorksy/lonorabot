"""0011 trading journal schema revision."""

from alembic import op
from lonora_db.schema import Base

revision = "0011_trading_journal"
down_revision = "0010_charts_watches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["ln_trading_accounts"].create(bind=op.get_bind())
    Base.metadata.tables["ln_trading_journal"].create(bind=op.get_bind())
    Base.metadata.tables["ln_financial_receipts"].create(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.tables["ln_financial_receipts"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_trading_journal"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_trading_accounts"].drop(bind=op.get_bind())
