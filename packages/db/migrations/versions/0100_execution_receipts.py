"""The Execution Receipt (mandate 10.3, 11.2) replaces the unused ln_financial_receipts.

``ln_execution_receipts`` holds one row per broker-confirmed operation: where its receipt
is posted. It cascades only with the journal row it reads (which is never deleted) and
the owner; the agent is attribution without a foreign key and the conversation anchor
is SET NULL, so deleting an agent or a conversation keeps the receipt (3.1.2).

Operations confirmed before this revision were shown as order lines at their journal
anchor. Each anchored confirmed operation gets its receipt at that same place, so the
conversation keeps one representation of it. Unanchored ones (the owner's own orders)
were never in a conversation and are not posted retroactively.

``ln_financial_receipts`` had no writer and cascaded with the agent and the thread. It is
dropped; the upgrade refuses if it holds any row rather than delete a receipt.
"""

import sqlalchemy as sa
from alembic import op

revision = "0100_execution_receipts"
down_revision = "0061_trade_approval_validity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    if bind.execute(sa.text("SELECT 1 FROM ln_financial_receipts LIMIT 1")).first():
        raise RuntimeError("ln_financial_receipts holds rows; refusing to drop receipts")
    op.create_table(
        "ln_execution_receipts",
        sa.Column("operation_id", sa.String(length=80), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("agent_id", sa.String(length=36), nullable=True),
        sa.Column("thread_id", sa.String(length=36), nullable=True),
        sa.Column("timeline_seq", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["operation_id"], ["ln_trading_journal.operation_id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["ln_owners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["thread_id"], ["ln_threads.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("operation_id"),
    )
    op.create_index(
        op.f("ix_ln_execution_receipts_owner_id"), "ln_execution_receipts", ["owner_id"]
    )
    op.create_index(
        "ln_execution_receipts_thread", "ln_execution_receipts", ["thread_id", "timeline_seq"]
    )
    op.execute(
        """
        INSERT INTO ln_execution_receipts
            (operation_id, owner_id, agent_id, thread_id, timeline_seq, created_at)
        SELECT operation_id, owner_id,
               NULLIF(result -> 'details' -> 'execution' ->> 'agent_id', ''),
               thread_id, timeline_seq, updated_at
        FROM ln_trading_journal
        WHERE status = 'confirmed' AND thread_id IS NOT NULL
        """
    )
    op.drop_index(op.f("ix_ln_financial_receipts_owner_id"), table_name="ln_financial_receipts")
    op.drop_table("ln_financial_receipts")


def downgrade() -> None:
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
        op.f("ix_ln_financial_receipts_owner_id"), "ln_financial_receipts", ["owner_id"]
    )
    op.drop_index("ln_execution_receipts_thread", table_name="ln_execution_receipts")
    op.drop_index(op.f("ix_ln_execution_receipts_owner_id"), table_name="ln_execution_receipts")
    op.drop_table("ln_execution_receipts")
