"""Owner action cards: durable, server-validated, single-use owner actions in chat."""

import sqlalchemy as sa
from alembic import op

revision = "0038_owner_actions"
down_revision = "0037_gateway_reliability"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_owner_actions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Durable record: agent and run ids are values; a deleted conversation keeps it.
        sa.Column("agent_id", sa.String(36), nullable=False),
        sa.Column("thread_id", sa.String(36), sa.ForeignKey("ln_threads.id", ondelete="SET NULL")),
        sa.Column("run_id", sa.String(36)),
        sa.Column("source", sa.String(8), nullable=False),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("subject", sa.String(160), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("payload_hash", sa.String(64), nullable=False),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("status_reason", sa.String(64)),
        sa.Column("result", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
        sa.Column("timeline_seq", sa.Integer()),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True)),
        sa.Column("decided_via", sa.String(16)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','confirmed','cancelled','expired','superseded')",
            name="ln_owner_action_status",
        ),
        sa.CheckConstraint("source IN ('agent','system')", name="ln_owner_action_source"),
    )
    op.create_index("ln_owner_action_owner_status", "ln_owner_actions", ["owner_id", "status"])
    op.create_index("ln_owner_action_thread", "ln_owner_actions", ["thread_id", "created_at"])
    op.create_index("ln_owner_action_subject", "ln_owner_actions", ["owner_id", "kind", "subject"])
    op.create_index(
        "ln_owner_action_pending_effect",
        "ln_owner_actions",
        ["agent_id", "kind", "payload_hash"],
        unique=True,
        postgresql_where=sa.text("status = 'pending'"),
    )


def downgrade() -> None:
    op.drop_index("ln_owner_action_pending_effect", table_name="ln_owner_actions")
    op.drop_index("ln_owner_action_subject", table_name="ln_owner_actions")
    op.drop_index("ln_owner_action_thread", table_name="ln_owner_actions")
    op.drop_index("ln_owner_action_owner_status", table_name="ln_owner_actions")
    op.drop_table("ln_owner_actions")
