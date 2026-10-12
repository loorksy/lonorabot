"""0001 foundation schema revision."""

from alembic import op
from lonora_db.schema import Base

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["ln_owners"].create(bind=op.get_bind())
    Base.metadata.tables["ln_sessions"].create(bind=op.get_bind())
    Base.metadata.tables["ln_agents"].create(bind=op.get_bind())
    Base.metadata.tables["ln_threads"].create(bind=op.get_bind())
    Base.metadata.tables["ln_messages"].create(bind=op.get_bind())
    Base.metadata.tables["ln_runs"].create(bind=op.get_bind())
    Base.metadata.tables["ln_events"].create(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.tables["ln_events"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_runs"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_messages"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_threads"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_agents"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_sessions"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_owners"].drop(bind=op.get_bind())
