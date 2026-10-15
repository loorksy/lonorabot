"""Explicit Personal identity and durable chronological approval anchors."""

import sqlalchemy as sa
from alembic import op

revision = "0018_agent_scope_timeline"
down_revision = "0017_agent_trading_binding"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ln_agents", sa.Column("role", sa.String(16), nullable=False, server_default="legacy")
    )
    op.execute(
        "UPDATE ln_agents SET role='specialist' WHERE trading_account_id IS NOT NULL AND trading_symbol IS NOT NULL"
    )
    op.create_check_constraint(
        "ln_agent_role", "ln_agents", "role IN ('personal','specialist','legacy')"
    )
    op.create_check_constraint(
        "ln_personal_scope",
        "ln_agents",
        "role != 'personal' OR (parent_id IS NULL AND trading_account_id IS NULL AND trading_symbol IS NULL)",
    )
    op.create_index(
        "ln_one_personal_agent",
        "ln_agents",
        ["owner_id"],
        unique=True,
        postgresql_where=sa.text("role = 'personal'"),
    )
    op.add_column("ln_trade_approvals", sa.Column("timeline_seq", sa.Integer(), nullable=True))
    # Legacy approval location is reconstructed once from durable message time, never fetch order.
    op.execute("""UPDATE ln_trade_approvals a SET timeline_seq = COALESCE(
        (SELECT MIN(m.seq) FROM ln_messages m WHERE m.thread_id=a.thread_id AND m.created_at >= a.created_at),
        (SELECT t.next_seq FROM ln_threads t WHERE t.id=a.thread_id))""")
    inspector = sa.inspect(op.get_bind())
    for constraint in inspector.get_unique_constraints("ln_steering"):
        if constraint["column_names"] == ["message_id"] and constraint["name"]:
            op.drop_constraint(constraint["name"], "ln_steering", type_="unique")
    op.create_unique_constraint("ln_run_message_steering", "ln_steering", ["run_id", "message_id"])


def downgrade() -> None:
    # Do not silently discard steering addressed to multiple agents.
    op.drop_constraint("ln_run_message_steering", "ln_steering", type_="unique")
    op.create_unique_constraint("ln_steering_message_id_key", "ln_steering", ["message_id"])
    op.drop_column("ln_trade_approvals", "timeline_seq")
    op.drop_index("ln_one_personal_agent", table_name="ln_agents")
    op.drop_constraint("ln_personal_scope", "ln_agents", type_="check")
    op.drop_constraint("ln_agent_role", "ln_agents", type_="check")
    op.drop_column("ln_agents", "role")
