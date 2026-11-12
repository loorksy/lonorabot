"""Trading restrictions are removed (mandate 4.4, 14.2.3); active ones end (14.3.18.6).

* Owner action cards of the removed ``lift_restriction`` kind are deleted (14.3.9): the
  contract no longer accepts that kind, and every one of them acted on a restriction.
* The restriction table is dropped; the admission path no longer reads it. Journal
  rows keep the ``admission_block`` evidence of what a restriction stopped before the
  broker.

The downgrade recreates the empty table as it stood before this revision; the
restrictions and the deleted cards are not restored.
"""

import sqlalchemy as sa
from alembic import op

revision = "0086_end_trading_restrictions"
down_revision = "0085_opportunity_pending_operations"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM ln_owner_actions WHERE kind = 'lift_restriction'"))
    op.drop_table("ln_trading_restrictions")


def downgrade() -> None:
    op.create_table(
        "ln_trading_restrictions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Durable record (0036): the account and agent ids are values, not links.
        sa.Column("account_id", sa.String(36), nullable=False),
        sa.Column("agent_id", sa.String(36)),
        sa.Column("symbol", sa.String(80)),
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
