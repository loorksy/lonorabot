"""Light agent goals and knowledge links, both owner resources bound to one agent.

``ln_agent_goals`` holds the «الأهداف» of an agent that does not trade (title,
description, done). A goal is a note for the owner and the agent: it carries no
schedule, no autonomy and no authority. ``ln_knowledge_links`` holds the «رابط» entries
of «المعرفة» (title, url, note), which the agent reads through its public client.
Both use the resource row shape; the downgrade drops them.
"""

import sqlalchemy as sa
from alembic import op

revision = "0057_agent_goals_knowledge_links"
down_revision = "0056_routine_title_run_at"
branch_labels = None
depends_on = None

TABLES = ("ln_agent_goals", "ln_knowledge_links")


def upgrade() -> None:
    for table in TABLES:
        op.create_table(
            table,
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
        op.create_index(op.f(f"ix_{table}_owner_id"), table, ["owner_id"], unique=False)


def downgrade() -> None:
    for table in reversed(TABLES):
        op.drop_index(op.f(f"ix_{table}_owner_id"), table_name=table)
        op.drop_table(table)
