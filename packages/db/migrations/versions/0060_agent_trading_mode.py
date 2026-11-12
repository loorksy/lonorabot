"""The agent's trading mode, Full or Ask (mandate 4.1), and the owner's standing
instruction to manage every position (3.3.4).

Every existing agent starts in Ask (14.3.18.1): no agent becomes Full without the owner's
tap on its Mandate card. Grants and the permission ladder keep working until they are
removed. The standing instruction is off until the owner gives it in chat. The downgrade
drops both columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "0060_agent_trading_mode"
down_revision = "0110_closed_trades"
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
    op.add_column(
        "ln_agents",
        sa.Column("manages_all_positions", sa.Boolean(), nullable=False, server_default=sa.false()),
    )


def downgrade() -> None:
    op.drop_column("ln_agents", "manages_all_positions")
    op.drop_constraint("ln_agent_trading_mode", "ln_agents", type_="check")
    op.drop_column("ln_agents", "trading_mode")
