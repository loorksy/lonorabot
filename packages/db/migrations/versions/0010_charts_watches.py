"""0010 charts watches schema revision."""

from alembic import op
from lonora_db.schema import Base

revision = "0010_charts_watches"
down_revision = "0009_broker_sessions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["ln_cloud_charts"].create(bind=op.get_bind())
    Base.metadata.tables["ln_chart_indicators"].create(bind=op.get_bind())
    Base.metadata.tables["ln_market_watches"].create(bind=op.get_bind())
    Base.metadata.tables["ln_market_wake_receipts"].create(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.tables["ln_market_wake_receipts"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_market_watches"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_chart_indicators"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_cloud_charts"].drop(bind=op.get_bind())
