"""Trading goals are removed (mandate 14.2.4); active goals end (mandate 14.3.18.6).

* A goal wake that has not finished (``trigger = 'goal'``, or a goal in its metadata) is
  cancelled with ``goal_removed``: its prompt names goal tools that no longer exist.
* Attention items of the removed ``goal_changed`` code are suppressed and stored as
  ``internal_update``, a code the contract still accepts.
* The goal and goal-decision tables are dropped. A decision named the journal operation
  it sent; the journal row keeps its own request, result and evidence, and is reconciled
  like any other operation.

The downgrade recreates the two empty tables as they stood before this revision; the
goals, the decisions and the cancelled runs are not restored.
"""

import sqlalchemy as sa
from alembic import op

revision = "0068_end_trading_goals"
down_revision = "0067_decouple_goal_wakes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    connection = op.get_bind()
    connection.execute(
        sa.text(
            "UPDATE ln_runs SET status = 'cancelled', error_code = 'goal_removed',"
            " lease_owner = NULL, lease_expires_at = NULL"
            " WHERE status NOT IN ('completed', 'failed', 'cancelled')"
            " AND (trigger = 'goal' OR (model_metadata::jsonb ->> 'goal_id') IS NOT NULL)"
        )
    )
    connection.execute(
        sa.text(
            "UPDATE ln_attention SET code = 'internal_update', status = 'suppressed'"
            " WHERE code = 'goal_changed'"
        )
    )
    op.drop_table("ln_goal_decisions")
    op.drop_table("ln_trading_goals")


def downgrade() -> None:
    op.create_table(
        "ln_trading_goals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        # Durable record (0036): the agent id is a value, the thread link is SET NULL.
        sa.Column("agent_id", sa.String(36)),
        sa.Column(
            "thread_id",
            sa.String(36),
            sa.ForeignKey(
                "ln_threads.id", ondelete="SET NULL", name="ln_trading_goals_thread_id_fkey"
            ),
        ),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("state", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_ln_trading_goals_owner_id", "ln_trading_goals", ["owner_id"])
    op.create_table(
        "ln_goal_decisions",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("goal_id", sa.String(36), nullable=False),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("step_id", sa.String(64), nullable=False),
        sa.Column("attempt", sa.Integer(), nullable=False),
        sa.Column("run_id", sa.String(36), sa.ForeignKey("ln_runs.id", ondelete="SET NULL")),
        sa.Column("operation_id", sa.String(80), nullable=False, unique=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("request", sa.JSON(), nullable=False),
        sa.Column("evidence", sa.JSON(), nullable=False),
        sa.Column("result", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("goal_id", "step_id", "attempt", name="goal_step_attempt"),
    )
    op.create_index("ix_ln_goal_decisions_goal_id", "ln_goal_decisions", ["goal_id"])
