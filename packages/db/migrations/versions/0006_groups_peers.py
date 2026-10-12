"""0006 groups peers schema revision."""

from alembic import op
from lonora_db.schema import Base

revision = "0006_groups_peers"
down_revision = "0005_routines"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["ln_groups"].create(bind=op.get_bind())
    Base.metadata.tables["ln_peer_messages"].create(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.tables["ln_peer_messages"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_groups"].drop(bind=op.get_bind())
