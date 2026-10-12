"""0009 broker sessions schema revision."""

from alembic import op
from lonora_db.schema import Base

revision = "0009_broker_sessions"
down_revision = "0008_voice"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["ln_broker_sessions"].create(bind=op.get_bind())
    Base.metadata.tables["ln_broker_subscriptions"].create(bind=op.get_bind())
    Base.metadata.tables["ln_economic_calendar"].create(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.tables["ln_economic_calendar"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_broker_subscriptions"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_broker_sessions"].drop(bind=op.get_bind())
