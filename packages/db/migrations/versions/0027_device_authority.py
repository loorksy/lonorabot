"""Signed single-use device challenges and one active Agent authority envelope."""

import sqlalchemy as sa
from alembic import op

revision = "0027_device_authority"
down_revision = "0026_attention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_device_credentials",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("credential_id", sa.String(2048), nullable=False, unique=True),
        sa.Column("public_key", sa.Text(), nullable=False),
        sa.Column("sign_count", sa.BigInteger(), nullable=False),
        sa.Column("revoked", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ln_device_credentials_owner_id", "ln_device_credentials", ["owner_id"])
    op.create_table(
        "ln_device_challenges",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("request_id", sa.String(36)),
        sa.Column("challenge", sa.Text(), nullable=False),
        sa.Column("binding_hash", sa.String(64), nullable=False),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ln_device_challenges_owner_id", "ln_device_challenges", ["owner_id"])
    op.create_table(
        "ln_super_bot_requests",
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
        sa.Column(
            "goal_id",
            sa.String(36),
            sa.ForeignKey("ln_trading_goals.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("mode", sa.String(16), nullable=False),
        sa.Column("status", sa.String(16), nullable=False),
        sa.Column("envelope", sa.JSON(), nullable=False),
        sa.Column("envelope_hash", sa.String(64), nullable=False),
        sa.Column(
            "device_id",
            sa.String(36),
            sa.ForeignKey("ln_device_credentials.id", ondelete="SET NULL"),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "mode IN ('advisory','supervised','autonomous')", name="ln_super_bot_mode"
        ),
        sa.CheckConstraint(
            "status IN ('pending','activated','rejected','expired','cancelled','paused','disabled')",
            name="ln_super_bot_status",
        ),
    )
    for key in ("owner_id", "agent_id", "goal_id"):
        op.create_index("ix_ln_super_bot_requests_" + key, "ln_super_bot_requests", [key])
    op.create_index(
        "ln_super_bot_active_goal",
        "ln_super_bot_requests",
        ["goal_id"],
        unique=True,
        postgresql_where=sa.text("status = 'activated'"),
        sqlite_where=sa.text("status = 'activated'"),
    )
    if op.get_bind().dialect.name == "postgresql":
        op.execute(
            "UPDATE ln_trading_goals SET state = jsonb_set(state::jsonb, '{autonomous}', 'false')::json WHERE state->>'autonomous' = 'true'"
        )


def downgrade() -> None:
    op.drop_table("ln_super_bot_requests")
    op.drop_table("ln_device_challenges")
    op.drop_table("ln_device_credentials")
