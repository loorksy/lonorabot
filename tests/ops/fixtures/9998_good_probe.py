"""Test-only revision: a working schema change, so restores of older backups must migrate."""

import sqlalchemy as sa
from alembic import op

revision = "9998_good_probe"
# build_test_images.sh replaces the placeholder with the base image's migration head.
down_revision = "__BASE_HEAD__"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table("ln_good_probe", sa.Column("id", sa.Integer, primary_key=True))


def downgrade() -> None:
    op.drop_table("ln_good_probe")
