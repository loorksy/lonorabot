"""Per-owner conversation state and the agent's creation template.

``ln_thread_prefs`` holds the owner's read cursor, marked-unread, mute, archive,
favourite, pin order (1..3) and the «مسح» history cursor per conversation, shared by web
and mobile. Every existing conversation starts read up to its latest message: before this
table the owner saw everything, so nothing old becomes unread.

``ln_agents.template`` persists the creation template (trading, general, research,
supervisor). It is backfilled from the creation record where one exists, else from the
focus pair (``trading``) and ``general`` for the other root agents; the personal agent and
delegated helpers keep NULL, their role being their type.
"""

from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0044_thread_prefs"
down_revision = "0043_owner_held_pauses"
branch_labels = None
depends_on = None

TEMPLATE_CHECK = "ln_agent_template"


def upgrade() -> None:
    op.create_table(
        "ln_thread_prefs",
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column(
            "thread_id",
            sa.String(36),
            sa.ForeignKey("ln_threads.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("last_read_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("marked_unread", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("muted", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("archived", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("favourite", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("pinned_order", sa.Integer()),
        sa.Column("hidden_before_seq", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "pinned_order IS NULL OR (pinned_order >= 1 AND pinned_order <= 3)",
            name="ln_thread_prefs_pinned_order",
        ),
    )
    op.execute(
        sa.text(
            "INSERT INTO ln_thread_prefs (owner_id, thread_id, last_read_seq, updated_at) "
            "SELECT owner_id, id, next_seq - 1, :now FROM ln_threads "
            "WHERE purpose = 'conversation'"
        ).bindparams(now=datetime.now(UTC))
    )
    op.add_column("ln_agents", sa.Column("template", sa.String(16)))
    op.create_check_constraint(
        TEMPLATE_CHECK,
        "ln_agents",
        "template IS NULL OR template IN ('trading','general','research','supervisor')",
    )
    op.execute(
        sa.text(
            "UPDATE ln_agents SET template = s.payload ->> 'template' FROM ln_settings s "
            "WHERE s.key LIKE 'agent-origin:%' AND s.payload ->> 'agent_id' = ln_agents.id "
            "AND s.payload ->> 'owner_id' = ln_agents.owner_id "
            "AND s.payload ->> 'template' IN ('trading','general','research','supervisor')"
        )
    )
    op.execute(
        sa.text(
            "UPDATE ln_agents SET template = 'trading' WHERE template IS NULL "
            "AND role IN ('general','specialist','legacy') AND trading_symbol IS NOT NULL"
        )
    )
    op.execute(
        sa.text(
            "UPDATE ln_agents SET template = 'general' WHERE template IS NULL "
            "AND role IN ('general','specialist','legacy')"
        )
    )


def downgrade() -> None:
    op.drop_constraint(TEMPLATE_CHECK, "ln_agents", type_="check")
    op.drop_column("ln_agents", "template")
    op.drop_table("ln_thread_prefs")
