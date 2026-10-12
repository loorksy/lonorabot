"""0004 memory skills schema revision."""

from alembic import op
from lonora_db.schema import Base

revision = "0004_memory_skills"
down_revision = "0003_run_leases"
branch_labels = None
depends_on = None


def upgrade() -> None:
    Base.metadata.tables["ln_memory"].create(bind=op.get_bind())
    Base.metadata.tables["ln_scratchpad"].create(bind=op.get_bind())
    Base.metadata.tables["ln_skills"].create(bind=op.get_bind())
    Base.metadata.tables["ln_semantic_memory"].create(bind=op.get_bind())
    Base.metadata.tables["ln_artifacts"].create(bind=op.get_bind())
    Base.metadata.tables["ln_boards"].create(bind=op.get_bind())
    Base.metadata.tables["ln_tickets"].create(bind=op.get_bind())
    Base.metadata.tables["ln_secrets"].create(bind=op.get_bind())
    Base.metadata.tables["ln_mcp_connections"].create(bind=op.get_bind())
    Base.metadata.tables["ln_integrations"].create(bind=op.get_bind())


def downgrade() -> None:
    Base.metadata.tables["ln_integrations"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_mcp_connections"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_secrets"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_tickets"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_boards"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_artifacts"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_semantic_memory"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_skills"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_scratchpad"].drop(bind=op.get_bind())
    Base.metadata.tables["ln_memory"].drop(bind=op.get_bind())
