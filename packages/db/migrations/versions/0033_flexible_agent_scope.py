"""Owner-created general agents and explicit default-market preferences."""

import sqlalchemy as sa
from alembic import op

revision = "0033_flexible_agent_scope"
down_revision = "0032_message_rich_content"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ln_agents",
        sa.Column("scope_mode", sa.String(16), nullable=False, server_default="fixed_market"),
    )
    op.add_column(
        "ln_agents", sa.Column("scope_revision", sa.Integer(), nullable=False, server_default="0")
    )
    op.drop_constraint("ln_agent_role", "ln_agents", type_="check")
    op.create_check_constraint(
        "ln_agent_role",
        "ln_agents",
        "role IN ('personal','general','specialist','delegated','legacy')",
    )
    op.create_check_constraint(
        "ln_agent_scope_mode", "ln_agents", "scope_mode IN ('fixed_market','flexible')"
    )
    op.create_check_constraint(
        "ln_agent_flexible_root",
        "ln_agents",
        "scope_mode != 'flexible' OR (parent_id IS NULL AND role IN ('general','specialist'))",
    )
    op.create_check_constraint(
        "ln_agent_general_scope",
        "ln_agents",
        "role != 'general' OR (scope_mode = 'flexible' AND trading_account_id IS NULL AND trading_symbol IS NULL)",
    )


def downgrade() -> None:
    # General identities cannot be represented by the old schema. Refuse a lossy downgrade.
    if op.get_bind().scalar(
        sa.text("SELECT count(*) FROM ln_agents WHERE scope_mode = 'flexible'")
    ):
        raise RuntimeError("Cannot downgrade while flexible agents exist")
    for name in (
        "ln_agent_general_scope",
        "ln_agent_flexible_root",
        "ln_agent_scope_mode",
        "ln_agent_role",
    ):
        op.drop_constraint(name, "ln_agents", type_="check")
    op.create_check_constraint(
        "ln_agent_role", "ln_agents", "role IN ('personal','specialist','delegated','legacy')"
    )
    op.drop_column("ln_agents", "scope_revision")
    op.drop_column("ln_agents", "scope_mode")
