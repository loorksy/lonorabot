"""Owner-defined chat lists and the folded search index on messages.

``ln_chat_lists`` (one name per owner) and ``ln_chat_list_members`` hold the custom list
chips of the conversation list, shared by web and mobile. The owner's search folds Arabic
(``lonora_core.search_fold``); the pg_trgm index on that exact expression over
``ln_messages.content`` serves the substring match. pg_trgm is a trusted extension: the
database owner can create it. The downgrade drops the lists and the index; the extension
stays, as infrastructure other databases may share.
"""

import sqlalchemy as sa
from alembic import op
from lonora_core.search_fold import folded_sql

revision = "0045_chat_lists"
down_revision = "0044_thread_prefs"
branch_labels = None
depends_on = None

INDEX = "ln_messages_content_folded"


def upgrade() -> None:
    op.create_table(
        "ln_chat_lists",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(30), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "name", name="ln_chat_list_name"),
    )
    op.create_index("ix_ln_chat_lists_owner_id", "ln_chat_lists", ["owner_id"])
    op.create_table(
        "ln_chat_list_members",
        sa.Column(
            "list_id",
            sa.String(36),
            sa.ForeignKey("ln_chat_lists.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "thread_id",
            sa.String(36),
            sa.ForeignKey("ln_threads.id", ondelete="CASCADE"),
            primary_key=True,
        ),
    )
    op.execute(sa.text("CREATE EXTENSION IF NOT EXISTS pg_trgm"))
    op.execute(
        sa.text(
            f"CREATE INDEX {INDEX} ON ln_messages USING gin "
            f"(({folded_sql('content')}) gin_trgm_ops)"
        )
    )


def downgrade() -> None:
    op.execute(sa.text(f"DROP INDEX IF EXISTS {INDEX}"))
    op.drop_table("ln_chat_list_members")
    op.drop_index("ix_ln_chat_lists_owner_id", table_name="ln_chat_lists")
    op.drop_table("ln_chat_lists")
