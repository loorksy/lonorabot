"""Conversation conveniences (UI phase 3, WP-D).

``ln_message_reactions`` holds one quick reaction per reactor and message: the owner
(``reactor = 'owner'``) or an agent (its id). ``ln_messages.suggested_reply`` is the
agent's optional next-reply suggestion (<= 60 characters) on a conversational answer;
``ln_messages.edited_from`` links an edited-and-resent owner message to the original,
which stays. ``ln_threads.options`` holds per-chat options (``web_search``). The
downgrade drops the table and the columns: reactions, suggestions, edit links and chat
options are conveniences, no owner decision or financial record depends on them.
"""

import sqlalchemy as sa
from alembic import op

revision = "0046_conversation_conveniences"
down_revision = "0058_skill_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_message_reactions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "message_id",
            sa.String(36),
            sa.ForeignKey("ln_messages.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("thread_id", sa.String(36), nullable=False),
        sa.Column("reactor", sa.String(36), nullable=False),
        sa.Column("emoji", sa.String(16), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("message_id", "reactor", name="ln_message_reaction_reactor"),
    )
    op.add_column("ln_messages", sa.Column("suggested_reply", sa.String(60)))
    op.add_column("ln_messages", sa.Column("edited_from", sa.String(36)))
    # One edit per original: the unique index also serves the superseded_by lookup.
    op.create_index("ix_ln_messages_edited_from", "ln_messages", ["edited_from"], unique=True)
    op.add_column(
        "ln_threads",
        sa.Column("options", sa.JSON(), nullable=False, server_default=sa.text("'{}'")),
    )


def downgrade() -> None:
    op.drop_column("ln_threads", "options")
    op.drop_index("ix_ln_messages_edited_from", table_name="ln_messages")
    op.drop_column("ln_messages", "edited_from")
    op.drop_column("ln_messages", "suggested_reply")
    op.drop_table("ln_message_reactions")
