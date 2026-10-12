"""0003 run leases schema revision."""

from alembic import op
from lonora_db.schema import Base

revision = "0003_run_leases"
down_revision = "0002_thread_sequences"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["ln_steering"].create(bind=op.get_bind())
    Base.metadata.tables["ln_gateways"].create(bind=op.get_bind())
    Base.metadata.tables["ln_effect_receipts"].create(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.tables["ln_effect_receipts"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_gateways"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_steering"].drop(bind=op.get_bind())
