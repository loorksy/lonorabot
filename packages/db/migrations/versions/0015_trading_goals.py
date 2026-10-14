"""Durable same-agent trading goals, decisions and existing scheduler linkage."""

import sqlalchemy as sa
from alembic import op

revision = "0015_trading_goals"
down_revision = "0014_agent_profiles"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_trading_goals",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("agent_id", sa.String(36), sa.ForeignKey("ln_agents.id", ondelete="CASCADE")),
        sa.Column("thread_id", sa.String(36), sa.ForeignKey("ln_threads.id", ondelete="CASCADE")),
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
        sa.Column(
            "goal_id",
            sa.String(36),
            sa.ForeignKey("ln_trading_goals.id", ondelete="CASCADE"),
            nullable=False,
        ),
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
    op.add_column(
        "ln_routines",
        sa.Column(
            "goal_id", sa.String(36), sa.ForeignKey("ln_trading_goals.id", ondelete="CASCADE")
        ),
    )
    op.add_column("ln_routines", sa.Column("step_id", sa.String(64)))


def downgrade() -> None:
    op.drop_column("ln_routines", "step_id")
    op.drop_column("ln_routines", "goal_id")
    op.drop_table("ln_goal_decisions")
    op.drop_table("ln_trading_goals")
