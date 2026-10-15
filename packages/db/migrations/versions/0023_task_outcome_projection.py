"""Repair persisted task/ticket outcome contradictions from pre-review releases."""

from alembic import op

revision = "0023_task_outcome_projection"
down_revision = "0022_delegated_scope"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute("""UPDATE ln_tickets SET payload = jsonb_set(payload::jsonb, '{status}',
        to_jsonb(CASE state->'task'->>'status'
          WHEN 'queued' THEN 'todo' WHEN 'running' THEN 'working'
          WHEN 'paused' THEN 'waiting' ELSE state->'task'->>'status' END))::json
        WHERE state->'task'->>'status' IN ('queued','running','waiting','paused','completed','failed','cancelled')""")


def downgrade() -> None:
    # Restoring contradictory outcome data is intentionally not a downgrade operation.
    pass
