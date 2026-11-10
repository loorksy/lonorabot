"""Test-only revision: a working schema change, so restores of older backups must migrate."""

import sqlalchemy as sa
from alembic import op

revision = "9998_good_probe"
down_revision = "0045_chat_lists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("ln_good_probe", sa.Column("id", sa.Integer, primary_key=True))


def downgrade() -> None:
    op.drop_table("ln_good_probe")
