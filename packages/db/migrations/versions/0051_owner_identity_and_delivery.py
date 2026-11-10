"""The owner's name and form of address (WP-H) and per-agent delivery rules (Q47).

``ln_owner_profile`` gains ``name`` and ``address`` («الاسم», «طريقة المخاطبة» of the
owner form); they are part of the attributed preferences change log.

``ln_agent_delivery_rules`` holds, per owner and agent, whether the agent's own alerts
show in the app, whether it may ring the owner, and a daily alert limit. No row means
the owner-wide reach-me policy alone. The quiet hours to the minute (also Q47) live in
the reach-me policy JSON (``quiet_start_minute`` / ``quiet_end_minute``) and need no
column; stored whole-hour policies keep working.
"""

import sqlalchemy as sa
from alembic import op

revision = "0051_owner_identity_and_delivery"
down_revision = "0045_chat_lists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ln_owner_profile", sa.Column("name", sa.String(80), nullable=True))
    op.add_column("ln_owner_profile", sa.Column("address", sa.String(80), nullable=True))
    op.create_table(
        "ln_agent_delivery_rules",
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("in_app", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("calls", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("daily_limit", sa.Integer(), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "daily_limit IS NULL OR (daily_limit >= 1 AND daily_limit <= 100)",
            name="ln_agent_delivery_rules_daily_limit",
        ),
    )


def downgrade() -> None:
    op.drop_table("ln_agent_delivery_rules")
    op.drop_column("ln_owner_profile", "address")
    op.drop_column("ln_owner_profile", "name")
