"""Signed bounded account delegation without a predeclared Goal plan."""

import sqlalchemy as sa
from alembic import op

revision = "0029_account_authority"
down_revision = "0028_analytical_workspace"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_account_authorities",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
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
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("ln_broker_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("status", sa.String(16), nullable=False, server_default="pending"),
        sa.Column("envelope", sa.JSON(), nullable=False),
        sa.Column("envelope_hash", sa.String(64), nullable=False),
        sa.Column(
            "device_id",
            sa.String(36),
            sa.ForeignKey("ln_device_credentials.id", ondelete="SET NULL"),
        ),
        sa.Column("activation_expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('pending','active','revoked','expired')", name="ln_account_authority_status"
        ),
    )
    for field in ("owner_id", "agent_id", "account_id"):
        op.create_index("ix_ln_account_authorities_" + field, "ln_account_authorities", [field])
    op.create_index(
        "ln_account_authority_active",
        "ln_account_authorities",
        ["agent_id", "account_id"],
        unique=True,
        postgresql_where=sa.text("status = 'active'"),
        sqlite_where=sa.text("status = 'active'"),
    )


def downgrade() -> None:
    op.drop_table("ln_account_authorities")
