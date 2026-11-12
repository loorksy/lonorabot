"""The closed-trade ledger (mandate 5.5.1).

``ln_closed_trades`` holds one row per trade whose position volume reached zero at the
broker (keyed by the deal that closed it), with its owner (3.3.4) and the realized P&L of its broker deals in the account
currency. ``ln_broker_deals`` keeps the deals of positions still open, read from broker
history since the cursor in ``ln_closed_trade_cursors``. New tables only: no stored
payload, request, fingerprint or operation id changes. The downgrade drops them.
"""

import sqlalchemy as sa
from alembic import op

revision = "0110_closed_trades"
down_revision = "0061_trade_approval_validity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_broker_deals",
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("account_id", sa.String(120), primary_key=True),
        sa.Column("deal_id", sa.String(120), primary_key=True),
        sa.Column("position_id", sa.String(120), nullable=False),
        sa.Column("time", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
    )
    op.create_index(
        "ln_broker_deals_position", "ln_broker_deals", ["owner_id", "account_id", "position_id"]
    )
    op.create_table(
        "ln_closed_trade_cursors",
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            primary_key=True,
        ),
        sa.Column("account_id", sa.String(120), primary_key=True),
        sa.Column("read_to", sa.DateTime(timezone=True), nullable=False),
        sa.Column("complete", sa.Boolean(), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "ln_closed_trades",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("account_id", sa.String(120), nullable=False),
        sa.Column("position_id", sa.String(120), nullable=False),
        sa.Column("closing_deal_id", sa.String(120), nullable=False),
        sa.Column("symbol", sa.String(80), nullable=False),
        sa.Column("side", sa.String(8), nullable=False),
        sa.Column("volume", sa.Numeric(38, 10)),
        sa.Column("agent_id", sa.String(36)),
        sa.Column("opening_operation_id", sa.String(80)),
        sa.Column("currency", sa.String(16), nullable=False),
        sa.Column("realized_pnl", sa.Numeric(38, 10)),
        sa.Column("opened_at", sa.DateTime(timezone=True)),
        sa.Column("closed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("deals", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint(
            "owner_id",
            "account_id",
            "position_id",
            "closing_deal_id",
            name="ln_closed_trade_closing_deal",
        ),
    )
    op.create_index(
        "ln_closed_trades_agent", "ln_closed_trades", ["owner_id", "agent_id", "closed_at"]
    )


def downgrade() -> None:
    op.drop_index("ln_closed_trades_agent", "ln_closed_trades")
    op.drop_table("ln_closed_trades")
    op.drop_table("ln_closed_trade_cursors")
    op.drop_index("ln_broker_deals_position", "ln_broker_deals")
    op.drop_table("ln_broker_deals")
