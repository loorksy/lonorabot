"""0001 foundation schema revision."""

import sqlalchemy as sa
from alembic import op

revision = "0001_foundation"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_owners",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("singleton", sa.Integer(), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("singleton = 1", name="one_owner"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email"),
        sa.UniqueConstraint("singleton"),
    )
    op.create_table(
        "ln_sessions",
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("csrf_hash", sa.String(length=64), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["ln_owners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("token_hash"),
    )
    op.create_table(
        "ln_agents",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("parent_id", sa.String(length=36), nullable=True),
        sa.Column("name", sa.String(length=80), nullable=False),
        sa.Column("avatar", sa.String(length=24), nullable=False),
        sa.Column("color", sa.String(length=7), nullable=False),
        sa.Column("instructions", sa.Text(), nullable=False),
        sa.Column("paused", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["ln_owners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["ln_agents.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ln_agents_owner_id"), "ln_agents", ["owner_id"], unique=False)
    op.create_table(
        "ln_threads",
        sa.Column("context_summary", sa.Text(), nullable=False),
        sa.Column("summary_seq", sa.Integer(), nullable=False),
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("group_id", sa.String(length=36), nullable=True),
        sa.Column("title", sa.String(length=160), nullable=False),
        sa.Column("next_seq", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["ln_agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["ln_owners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ln_threads_group_id"), "ln_threads", ["group_id"], unique=False)
    op.create_index(op.f("ix_ln_threads_owner_id"), "ln_threads", ["owner_id"], unique=False)
    op.create_table(
        "ln_messages",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("seq", sa.Integer(), nullable=False),
        sa.Column("role", sa.String(length=16), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("client_nonce", sa.String(length=100), nullable=True),
        sa.Column("reply_to", sa.String(length=36), nullable=True),
        sa.Column("attachment_ids", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("role IN ('user','assistant','system','tool')"),
        sa.ForeignKeyConstraint(["agent_id"], ["ln_agents.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["thread_id"], ["ln_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("thread_id", "client_nonce"),
        sa.UniqueConstraint("thread_id", "seq"),
    )
    op.create_index(op.f("ix_ln_messages_thread_id"), "ln_messages", ["thread_id"], unique=False)
    op.create_table(
        "ln_runs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("parent_run_id", sa.String(length=36), nullable=True),
        sa.Column("trigger", sa.String(length=32), nullable=False),
        sa.Column("prompt", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("input_seq", sa.Integer(), nullable=False),
        sa.Column("lease_owner", sa.String(length=120), nullable=True),
        sa.Column("lease_fence", sa.Integer(), nullable=False),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("execution_state", sa.JSON(), nullable=False),
        sa.Column("model_metadata", sa.JSON(), nullable=False),
        sa.Column("error_code", sa.String(length=80), nullable=True),
        sa.Column("result", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','leased','running','waiting_input','waiting_takeover','completed','failed','cancelled')"
        ),
        sa.ForeignKeyConstraint(["agent_id"], ["ln_agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["ln_threads.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_ln_runs_parent_run_id"), "ln_runs", ["parent_run_id"], unique=False)
    op.create_index(op.f("ix_ln_runs_thread_id"), "ln_runs", ["thread_id"], unique=False)
    op.create_index(
        "ln_run_claim", "ln_runs", ["status", "lease_expires_at", "created_at"], unique=False
    )
    op.create_table(
        "ln_events",
        sa.Column("cursor", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("thread_id", sa.String(length=36), nullable=True),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("run_id", sa.String(length=36), nullable=True),
        sa.Column("kind", sa.String(length=80), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["ln_owners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("cursor"),
    )
    op.create_index(op.f("ix_ln_events_owner_id"), "ln_events", ["owner_id"], unique=False)
    op.create_index(op.f("ix_ln_events_thread_id"), "ln_events", ["thread_id"], unique=False)


def downgrade() -> None:
    op.drop_table("ln_events")
    op.drop_table("ln_runs")
    op.drop_table("ln_messages")
    op.drop_table("ln_threads")
    op.drop_table("ln_agents")
    op.drop_table("ln_sessions")
    op.drop_table("ln_owners")
