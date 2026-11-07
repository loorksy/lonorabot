"""Durable, scoped, expiring owner restrictions on financial admission."""

import sqlalchemy as sa
from alembic import op

revision = "0034_trading_restrictions"
down_revision = "0033_flexible_agent_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_trading_restrictions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "account_id",
            sa.String(36),
            sa.ForeignKey("ln_broker_sessions.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("ln_agents.id", ondelete="CASCADE")),
        sa.Column("symbol", sa.String(80)),
        # False only when the broker catalog could not be read and the symbol was kept as
        # given; a readable catalog must list the symbol for a restriction to be created.
        sa.Column("symbol_verified", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("action_class", sa.String(24), nullable=False),
        sa.Column("valid_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("valid_until", sa.DateTime(timezone=True)),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column(
            "source_message_id",
            sa.String(36),
            sa.ForeignKey("ln_messages.id", ondelete="SET NULL"),
        ),
        sa.Column("source_run_id", sa.String(36)),
        sa.Column("reason", sa.Text(), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(8), nullable=False),
        sa.Column(
            "created_by_agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="SET NULL"),
        ),
        sa.Column(
            "applies_to_owner_manual", sa.Boolean(), nullable=False, server_default=sa.false()
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_reason", sa.Text()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "action_class IN ('no_new_entries','no_risk_increase','all_mutations')",
            name="ln_trading_restriction_action_class",
        ),
        sa.CheckConstraint(
            "source IN ('owner_ui','owner_message','agent')", name="ln_trading_restriction_source"
        ),
        sa.CheckConstraint(
            "created_by IN ('owner','agent')", name="ln_trading_restriction_creator"
        ),
        sa.CheckConstraint(
            "valid_until IS NULL OR valid_until > valid_from",
            name="ln_trading_restriction_window",
        ),
    )
    op.create_index("ix_ln_trading_restrictions_owner_id", "ln_trading_restrictions", ["owner_id"])
    op.create_index(
        "ln_trading_restriction_scope",
        "ln_trading_restrictions",
        ["owner_id", "account_id", "revoked_at"],
    )


def downgrade() -> None:
    # Dropping restrictions would silently re-admit what the owner prohibited.
    if op.get_bind().scalar(
        sa.text(
            "SELECT count(*) FROM ln_trading_restrictions "
            "WHERE revoked_at IS NULL AND (valid_until IS NULL OR valid_until > now())"
        )
    ):
        raise RuntimeError("Cannot downgrade while trading restrictions are in force")
    op.drop_table("ln_trading_restrictions")
