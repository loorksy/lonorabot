"""One durable attention projection with source-event provenance."""

import sqlalchemy as sa
from alembic import op

revision = "0026_attention"
down_revision = "0025_shadow_execution"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_attention",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "thread_id",
            sa.String(36),
            sa.ForeignKey("ln_threads.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("logical_key", sa.String(64), nullable=False),
        sa.Column("coalesce_key", sa.String(64), nullable=False),
        sa.Column("importance", sa.String(24), nullable=False),
        sa.Column("code", sa.String(40), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("parameters", sa.JSON(), nullable=False),
        sa.Column("source_events", sa.JSON(), nullable=False),
        sa.Column("source_count", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("due_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "logical_key", name="ln_attention_logical_key"),
        sa.CheckConstraint(
            "status IN ('pending','ready','seen','suppressed')", name="ln_attention_status"
        ),
    )
    op.create_index("ix_ln_attention_owner_id", "ln_attention", ["owner_id"])
    op.create_index("ix_ln_attention_coalesce_key", "ln_attention", ["coalesce_key"])
    op.create_index("ln_attention_due", "ln_attention", ["status", "due_at"])


def downgrade() -> None:
    op.drop_table("ln_attention")
