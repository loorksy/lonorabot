"""0008 voice schema revision."""

import sqlalchemy as sa
from alembic import op

revision = "0008_voice"
down_revision = "0007_global_models"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_voice",
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("thread_id", sa.String(length=36), nullable=True),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["ln_agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["ln_owners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["ln_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ln_voice_owner_id"), "ln_voice", ["owner_id"], unique=False)


def downgrade() -> None:
    op.drop_table("ln_voice")
