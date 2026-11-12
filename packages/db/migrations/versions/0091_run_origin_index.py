"""Index runs by the conversation they report to (VISION 11.6).

A background run's question is copied into the conversation it reports to, so a
conversation's history and its run list also read the runs whose
``model_metadata->>'origin_thread_id'`` names it. This partial expression index keeps that
lookup from scanning every run.
"""

from alembic import op

revision = "0091_run_origin_index"
down_revision = "0190_drop_unused_resource_tables"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "CREATE INDEX ln_run_origin_thread ON ln_runs ((model_metadata ->> 'origin_thread_id'))"
        " WHERE (model_metadata ->> 'origin_thread_id') IS NOT NULL"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS ln_run_origin_thread")
