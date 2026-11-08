"""Bounded per-agent recency of long-tail tools promoted into later Runs."""

import sqlalchemy as sa
from alembic import op

revision = "0035_agent_tool_usage"
down_revision = "0034_trading_restrictions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_agent_tool_usage",
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("tool_name", sa.String(100), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("uses", sa.Integer(), nullable=False, server_default="1"),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ln_agent_tool_usage_owner_id", "ln_agent_tool_usage", ["owner_id"])


def downgrade() -> None:
    op.drop_index("ix_ln_agent_tool_usage_owner_id", table_name="ln_agent_tool_usage")
    op.drop_table("ln_agent_tool_usage")
