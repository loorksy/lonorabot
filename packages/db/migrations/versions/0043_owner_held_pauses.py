"""The owner's own pause is recorded, and a supervisor's hold outlives its supervisor.

A pause or cancel the owner makes on an agent's work (the agent itself, a Task, a routine
or a watch) is a hold row even when no supervisor was involved: ``source='owner'`` with
no holder, so the paused agent never lifts it on its own initiative. A hold whose
supervisor is deleted stays in force as the owner's pause: ``holder_agent_id`` becomes
nullable with ``ON DELETE SET NULL`` (the delete first makes the hold the owner's).

The downgrade refuses while a live hold has no holder (the old schema cannot keep the
owner's pause) and drops released holder-less rows, which only ever recorded history.
"""

import sqlalchemy as sa
from alembic import op

revision = "0043_owner_held_pauses"
down_revision = "0042_trusted_sources"
branch_labels = None
depends_on = None

TABLE = "ln_supervision_holds"
HOLDER_FK = "ln_supervision_holds_holder_agent_id_fkey"


def upgrade() -> None:
    op.drop_constraint(HOLDER_FK, TABLE, type_="foreignkey")
    op.alter_column(TABLE, "holder_agent_id", existing_type=sa.String(36), nullable=True)
    op.create_foreign_key(
        HOLDER_FK, TABLE, "ln_agents", ["holder_agent_id"], ["id"], ondelete="SET NULL"
    )


def downgrade() -> None:
    connection = op.get_bind()
    if connection.scalar(
        sa.text(
            "SELECT count(*) FROM "
            + TABLE
            + " WHERE holder_agent_id IS NULL AND released_at IS NULL"
        )
    ):
        raise RuntimeError("Cannot downgrade while the owner holds a pause on an agent's work")
    connection.execute(sa.text("DELETE FROM " + TABLE + " WHERE holder_agent_id IS NULL"))
    op.drop_constraint(HOLDER_FK, TABLE, type_="foreignkey")
    op.alter_column(TABLE, "holder_agent_id", existing_type=sa.String(36), nullable=False)
    op.create_foreign_key(
        HOLDER_FK, TABLE, "ln_agents", ["holder_agent_id"], ["id"], ondelete="CASCADE"
    )
