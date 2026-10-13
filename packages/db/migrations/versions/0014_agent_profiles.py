"""Persist bot titles and descriptions; existing agents keep their behavior."""

import sqlalchemy as sa
from alembic import op

revision = "0014_agent_profiles"
down_revision = "0013_market_snapshots"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ln_agents", sa.Column("title", sa.String(160), nullable=False, server_default="")
    )
    op.add_column(
        "ln_agents", sa.Column("description", sa.Text(), nullable=False, server_default="")
    )


def downgrade() -> None:
    op.drop_column("ln_agents", "description")
    op.drop_column("ln_agents", "title")
