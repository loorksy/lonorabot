"""Personal visibility cannot mint unrestricted financial descendants."""

import sqlalchemy as sa
from alembic import op

revision = "0022_delegated_scope"
down_revision = "0021_thread_work_lane"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("ln_agent_role", "ln_agents", type_="check")
    op.create_check_constraint(
        "ln_agent_role", "ln_agents", "role IN ('personal','specialist','delegated','legacy')"
    )
    op.execute("""WITH RECURSIVE research(id) AS (
        SELECT id FROM ln_agents WHERE parent_id IS NOT NULL
        AND trading_account_id IS NULL AND trading_symbol IS NULL AND role != 'personal'
        UNION SELECT a.id FROM ln_agents a JOIN research r ON a.parent_id=r.id
    ) UPDATE ln_agents SET role='delegated', trading_account_id=NULL, trading_symbol=NULL
      WHERE id IN (SELECT id FROM research)""")
    # A deleted parent leaves the delegated role intact (parent FK uses SET NULL).
    op.create_check_constraint(
        "ln_delegated_scope",
        "ln_agents",
        "role != 'delegated' OR (trading_account_id IS NULL AND trading_symbol IS NULL)",
    )


def downgrade() -> None:
    if op.get_bind().scalar(sa.text("SELECT count(*) FROM ln_agents WHERE role='delegated'")):
        raise RuntimeError("delegated_scope_downgrade_unsafe")
    op.drop_constraint("ln_delegated_scope", "ln_agents", type_="check")
    op.drop_constraint("ln_agent_role", "ln_agents", type_="check")
    op.create_check_constraint(
        "ln_agent_role", "ln_agents", "role IN ('personal','specialist','legacy')"
    )
