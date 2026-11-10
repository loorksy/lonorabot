"""Routines gain an owner-visible title and a one-shot ``run_at``.

``title`` names a schedule in «المهام المجدولة» (empty for older routines: the page shows
the prompt). ``run_at`` marks a one-shot routine («مرة واحدة»): it fires once at that
time and switches itself off. Both are nullable, so existing routines keep their meaning.
"""

import sqlalchemy as sa
from alembic import op

revision = "0056_routine_title_run_at"
down_revision = "0045_chat_lists"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ln_routines", sa.Column("title", sa.String(160), nullable=True))
    op.add_column("ln_routines", sa.Column("run_at", sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    op.drop_column("ln_routines", "run_at")
    op.drop_column("ln_routines", "title")
