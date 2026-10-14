"""Immutable broker account and exact market selection for new bots."""

import sqlalchemy as sa
from alembic import op

revision = "0017_agent_trading_binding"
down_revision = "0016_trade_approvals"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ln_agents", sa.Column("trading_account_id", sa.String(36), nullable=True))
    op.add_column("ln_agents", sa.Column("trading_symbol", sa.String(80), nullable=True))
    op.create_check_constraint(
        "ln_agent_trading_binding_paired",
        "ln_agents",
        "(trading_account_id IS NULL AND trading_symbol IS NULL) OR (trading_account_id IS NOT NULL AND trading_symbol IS NOT NULL)",
    )


def downgrade() -> None:
    op.drop_constraint("ln_agent_trading_binding_paired", "ln_agents", type_="check")
    op.drop_column("ln_agents", "trading_symbol")
    op.drop_column("ln_agents", "trading_account_id")
