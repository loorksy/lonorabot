"""Test-only revision: changes the schema so a rollback must restore the database."""

import sqlalchemy as sa
from alembic import op

revision = "9999_broken_probe"
down_revision = "0045_chat_lists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("ln_broken_probe", sa.Column("id", sa.Integer, primary_key=True))


def downgrade() -> None:
    op.drop_table("ln_broken_probe")
