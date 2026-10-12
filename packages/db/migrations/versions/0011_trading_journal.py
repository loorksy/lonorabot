"""0011 trading journal schema revision."""

import sqlalchemy as sa
from alembic import op

revision = "0011_trading_journal"
down_revision = "0010_charts_watches"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_trading_accounts",
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
    op.create_index(
        op.f("ix_ln_trading_accounts_owner_id"), "ln_trading_accounts", ["owner_id"], unique=False
    )
    op.create_table(
        "ln_trading_journal",
        sa.Column("operation_id", sa.String(length=80), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("account_id", sa.String(length=120), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(length=24), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["ln_owners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("operation_id"),
    )
    op.create_index(
        op.f("ix_ln_trading_journal_account_id"), "ln_trading_journal", ["account_id"], unique=False
    )
    op.create_index(
        op.f("ix_ln_trading_journal_status"), "ln_trading_journal", ["status"], unique=False
    )
    op.create_table(
        "ln_financial_receipts",
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
    op.create_index(
        op.f("ix_ln_financial_receipts_owner_id"),
        "ln_financial_receipts",
        ["owner_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_table("ln_financial_receipts")
    op.drop_table("ln_trading_journal")
    op.drop_table("ln_trading_accounts")
