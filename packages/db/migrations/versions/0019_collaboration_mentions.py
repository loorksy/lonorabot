"""Durable collaboration and stable message mention identities."""

import sqlalchemy as sa
from alembic import op

revision = "0019_collaboration_mentions"
down_revision = "0018_agent_scope_timeline"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ln_messages",
        sa.Column("mentions", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )
    op.create_table(
        "ln_collaboration_sessions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("ln_agents.id", ondelete="CASCADE")),
        sa.Column("thread_id", sa.String(36), sa.ForeignKey("ln_threads.id", ondelete="CASCADE")),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index(
        "ix_ln_collaboration_sessions_owner_id", "ln_collaboration_sessions", ["owner_id"]
    )
    op.create_index(
        "ln_collaboration_origin", "ln_collaboration_sessions", ["thread_id", "updated_at"]
    )


def downgrade() -> None:
    op.drop_table("ln_collaboration_sessions")
    op.drop_column("ln_messages", "mentions")
