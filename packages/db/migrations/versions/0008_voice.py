"""0008 voice schema revision."""

from alembic import op
from lonora_db.schema import Base

revision = "0008_voice"
down_revision = "0007_global_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["ln_voice"].create(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.tables["ln_voice"].drop(bind=op.get_bind())
