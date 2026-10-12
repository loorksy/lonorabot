"""0005 routines schema revision."""

from alembic import op
from lonora_db.schema import Base

revision = "0005_routines"
down_revision = "0004_memory_skills"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["ln_routines"].create(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.tables["ln_routines"].drop(bind=op.get_bind())
