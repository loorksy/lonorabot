"""Keep internal same-agent work out of the public conversation catalogue."""

import sqlalchemy as sa
from alembic import op

revision = "0021_thread_work_lane"
down_revision = "0020_approval_broker_snapshot"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "ln_threads",
        sa.Column("purpose", sa.String(16), nullable=False, server_default="conversation"),
    )
    op.create_check_constraint(
        "ln_thread_purpose", "ln_threads", "purpose IN ('conversation','work')"
    )
    op.execute("""UPDATE ln_threads t SET purpose='work' WHERE EXISTS
        (SELECT 1 FROM ln_runs r WHERE r.thread_id=t.id AND (r.trigger='subagent' OR r.model_metadata->>'task_id' IS NOT NULL))
        AND NOT EXISTS (SELECT 1 FROM ln_messages m WHERE m.thread_id=t.id AND m.role='user')""")


def downgrade() -> None:
    op.drop_constraint("ln_thread_purpose", "ln_threads", type_="check")
    op.drop_column("ln_threads", "purpose")
