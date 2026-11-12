"""The agent's own `lonora` CLI token (mandate 7.3.3).

One row per agent; deleting the agent deletes the row, which revokes the token. New
table, no stored payload changes; the downgrade drops it.
"""

import sqlalchemy as sa
from alembic import op

revision = "0165_agent_cli_tokens"
down_revision = "0070_secret_scopes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_agent_cli_tokens",
        sa.Column("agent_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["ln_agents.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["ln_owners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("agent_id"),
        sa.UniqueConstraint("token_hash"),
    )


def downgrade() -> None:
    op.drop_table("ln_agent_cli_tokens")
