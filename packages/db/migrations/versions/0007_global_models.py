"""0007 global models schema revision."""

from alembic import op
from lonora_db.schema import Base

revision = "0007_global_models"
down_revision = "0006_groups_peers"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["ln_settings"].create(bind=op.get_bind())
    Base.metadata.tables["ln_model_backups"].create(bind=op.get_bind())
    Base.metadata.tables["ln_usage"].create(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.tables["ln_usage"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_model_backups"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_settings"].drop(bind=op.get_bind())
