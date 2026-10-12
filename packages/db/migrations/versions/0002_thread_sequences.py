"""0002 thread sequences schema revision."""

from alembic import op

revision = "0002_thread_sequences"
down_revision = "0001_foundation"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_index("ln_message_sequence_page", "ln_messages", ["thread_id", "seq"])


def downgrade() -> None:
    op.drop_index("ln_message_sequence_page", table_name="ln_messages")
