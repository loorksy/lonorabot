"""0190 drop two resource tables nothing ever read or wrote (mandate 13.2).

``ln_broker_subscriptions`` and ``ln_chart_indicators`` were created with their
repositories (0009, 0010), and no code ever wrote a row. Market data subscriptions
live in the broker adapter's stream (``metaapi.py`` ``subscribe_to_market_data``), and a
chart's indicators live in its own state (``ChartState.indicators`` on ``ln_cloud_charts``).
"""

import sqlalchemy as sa
from alembic import op

revision = "0190_drop_unused_resource_tables"
down_revision = "0131_agent_model_owner_only"
branch_labels = None
depends_on = None

TABLES = ("ln_broker_subscriptions", "ln_chart_indicators")


def upgrade() -> None:
    for table in TABLES:
        op.drop_index(op.f("ix_" + table + "_owner_id"), table_name=table)
        op.drop_table(table)


def downgrade() -> None:
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
        op.create_index(op.f("ix_" + table + "_owner_id"), table, ["owner_id"], unique=False)
