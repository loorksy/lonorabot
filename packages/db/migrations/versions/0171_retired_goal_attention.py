"""Attention rows of the removed trading goals are deleted.

Trading goals were removed (mandate 14.2.4, migration 0068) together with the
``goal_changed`` attention code, but stored ``goal_changed`` rows stayed. Every item is
read through ``AttentionNotification`` (its code is a closed set), so one such row made
the owner's attention routes fail. The rows only said that a goal changed; they are
projection rows, and their source events and effect receipts stay. The downgrade
restores nothing.
"""

import sqlalchemy as sa
from alembic import op

revision = "0171_retired_goal_attention"
down_revision = "0170_broker_health_attention"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM ln_attention WHERE code = 'goal_changed'"))


def downgrade() -> None:
    pass
