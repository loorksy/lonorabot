"""Financial, authority and evidence records outlive the agents, threads and runs they name.

Contextual links (the conversation, the Run) become ``ON DELETE SET NULL``. Identity links
(the agent, the broker account, the goal) keep their id as a plain denormalized column, so
deleting the parent never removes or rewrites the record: a NULL agent on a restriction
would otherwise mean "every agent".
"""

import sqlalchemy as sa
from alembic import op

revision = "0036_durable_records"
down_revision = "0035_agent_tool_usage"
branch_labels = None
depends_on = None

# (table, column, parent table) whose cascade is removed and whose id is kept as a value.
IDENTITY_LINKS = (
    ("ln_account_authorities", "agent_id", "ln_agents"),
    ("ln_account_authorities", "account_id", "ln_broker_sessions"),
    ("ln_super_bot_requests", "agent_id", "ln_agents"),
    ("ln_super_bot_requests", "goal_id", "ln_trading_goals"),
    ("ln_trade_approvals", "agent_id", "ln_agents"),
    ("ln_goal_decisions", "goal_id", "ln_trading_goals"),
    ("ln_trading_goals", "agent_id", "ln_agents"),
    ("ln_trading_restrictions", "account_id", "ln_broker_sessions"),
    ("ln_trading_restrictions", "agent_id", "ln_agents"),
)
# (table, column, parent table, was NOT NULL) that now survive their parent as NULL.
CONTEXT_LINKS = (
    ("ln_account_authorities", "thread_id", "ln_threads", True),
    ("ln_super_bot_requests", "thread_id", "ln_threads", True),
    ("ln_trade_approvals", "run_id", "ln_runs", True),
    ("ln_trade_approvals", "thread_id", "ln_threads", True),
    ("ln_trading_goals", "thread_id", "ln_threads", False),
)


def constraint(table: str, column: str) -> str:
    return table + "_" + column + "_fkey"


def upgrade() -> None:
    for table, column, _ in IDENTITY_LINKS:
        op.drop_constraint(constraint(table, column), table, type_="foreignkey")
    for table, column, parent, required in CONTEXT_LINKS:
        op.drop_constraint(constraint(table, column), table, type_="foreignkey")
        if required:
            op.alter_column(table, column, existing_type=sa.String(36), nullable=True)
        op.create_foreign_key(
            constraint(table, column), table, parent, [column], ["id"], ondelete="SET NULL"
        )


def downgrade() -> None:
    connection = op.get_bind()
    for table, column, _, required in CONTEXT_LINKS:
        if required and connection.scalar(
            sa.text("SELECT count(*) FROM " + table + " WHERE " + column + " IS NULL")
        ):
            raise RuntimeError("Cannot downgrade while durable records outlive their parents")
    for table, column, parent in IDENTITY_LINKS:
        if connection.scalar(
            sa.text(
                "SELECT count(*) FROM "
                + table
                + " child WHERE child."
                + column
                + " IS NOT NULL AND NOT EXISTS (SELECT 1 FROM "
                + parent
                + " parent WHERE parent.id = child."
                + column
                + ")"
            )
        ):
            raise RuntimeError("Cannot downgrade while durable records outlive their parents")
    for table, column, parent, required in CONTEXT_LINKS:
        op.drop_constraint(constraint(table, column), table, type_="foreignkey")
        if required:
            op.alter_column(table, column, existing_type=sa.String(36), nullable=False)
        op.create_foreign_key(
            constraint(table, column), table, parent, [column], ["id"], ondelete="CASCADE"
        )
    for table, column, parent in IDENTITY_LINKS:
        op.create_foreign_key(
            constraint(table, column), table, parent, [column], ["id"], ondelete="CASCADE"
        )
