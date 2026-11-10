"""Conversation anchors for trading journal operations.

``ln_trading_journal.thread_id`` and ``timeline_seq`` record the conversation and the
message seq at the moment an agent Run of that conversation requested the operation, so
the chat can place one order line per operation in its timeline (like
``ln_trade_approvals.timeline_seq``; a deleted conversation clears the anchor, the
operation stays). They are presentation metadata only: no execution,
authority or reconciliation path reads them. Operations from the owner's own controls
or from background transitions carry no anchor.
"""

import sqlalchemy as sa
from alembic import op

revision = "0047_conversation_anchors"
down_revision = "0045_chat_lists"
branch_labels = None
depends_on = None

INDEX = "ln_trading_journal_thread"


def upgrade() -> None:
    op.add_column(
        "ln_trading_journal",
        sa.Column(
            "thread_id",
            sa.String(36),
            sa.ForeignKey("ln_threads.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column("ln_trading_journal", sa.Column("timeline_seq", sa.Integer(), nullable=True))
    op.create_index(INDEX, "ln_trading_journal", ["thread_id", "updated_at"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name="ln_trading_journal")
    op.drop_column("ln_trading_journal", "timeline_seq")
    op.drop_column("ln_trading_journal", "thread_id")
