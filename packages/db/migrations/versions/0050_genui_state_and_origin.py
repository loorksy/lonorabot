"""Generative UI v2: who wrote a message, a card submission and a card's saved values.

``ln_messages.origin`` is ``owner`` for the owner's own words, ``ui_submit`` for a card's
send (its text composed by the server from the intent registry) and ``ui_follow_up`` for a
v1 follow-up tap. ``ui_submit`` holds ``{source_message_id, part, intent, data, run_id,
started_at?, superseded_at?}``; ``ui_state`` holds a card's values per part on the assistant
message that carries it (GENUI_PLAN §8.2, §8.4, §9.3). Existing rows are the owner's words;
v1 follow-up taps are marked by the same rule the server applies at write time.
"""

import sqlalchemy as sa
from alembic import op

revision = "0050_genui_state_and_origin"
down_revision = "0045_chat_lists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ln_messages",
        sa.Column("origin", sa.String(16), nullable=False, server_default="owner"),
    )
    op.add_column("ln_messages", sa.Column("ui_submit", sa.JSON(), nullable=True))
    op.add_column("ln_messages", sa.Column("ui_state", sa.JSON(), nullable=True))
    op.create_check_constraint(
        "ln_message_origin", "ln_messages", "origin IN ('owner','ui_submit','ui_follow_up')"
    )
    # Backfill: a plain owner message equal to a v1 follow-up action text of a card among
    # the thread's 20 latest earlier assistant messages was a tap, not the owner's words.
    op.execute(
        """
        UPDATE ln_messages AS m SET origin = 'ui_follow_up'
        WHERE m.role = 'user' AND m.agent_id IS NULL AND EXISTS (
            SELECT 1 FROM (
                SELECT a.rich_content FROM ln_messages AS a
                WHERE a.thread_id = m.thread_id AND a.role = 'assistant' AND a.seq < m.seq
                ORDER BY a.seq DESC LIMIT 20
            ) AS recent
            WHERE recent.rich_content IS NOT NULL
              AND jsonb_path_exists(
                    recent.rich_content::jsonb,
                    '$.** ? (@.kind == "follow_up" && @.text == $text)',
                    jsonb_build_object('text', m.content)
                  )
        )
        """
    )


def downgrade() -> None:
    op.drop_constraint("ln_message_origin", "ln_messages", type_="check")
    op.drop_column("ln_messages", "ui_state")
    op.drop_column("ln_messages", "ui_submit")
    op.drop_column("ln_messages", "origin")
