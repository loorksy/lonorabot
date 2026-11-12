"""The agent's trading mode: Full or Ask (mandate 4.1).

Every existing agent starts in Ask (14.3.18.1): no agent becomes Full without the owner's
tap on its Mandate card. Grants and the permission ladder keep working until they are
removed; the column only adds the new switch. The downgrade drops the column.
"""

import sqlalchemy as sa
from alembic import op

revision = "0060_agent_trading_mode"
down_revision = "0050_genui_state_and_origin"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ln_agents",
        sa.Column("trading_mode", sa.String(length=8), nullable=False, server_default="ask"),
    )
    op.create_check_constraint(
        "ln_agent_trading_mode", "ln_agents", "trading_mode IN ('full','ask')"
    )


def downgrade() -> None:
    op.drop_constraint("ln_agent_trading_mode", "ln_agents", type_="check")
    op.drop_column("ln_agents", "trading_mode")
