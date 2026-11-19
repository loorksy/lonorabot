"""A pause an agent made from the owner's message is the owner's (mandate 4.7.2).

Only the owner lifts a pause the owner made. From this revision a ``source='owner'``
hold with a ``source_message_id`` is one the owner asked for in chat, which the owner
also lifts by asking in chat. Before it, an ``'owner'`` hold was always control-only,
even when it began as a chat pause the owner then paused or cancelled with a control
(its message id stayed): those rows lose the message id first, so they stay
control-only. Then a hold recorded with ``source='owner_message'`` (an agent paused
work because the owner asked in chat) becomes ``source='owner'``; its holder and
``source_message_id`` stay. The CHECK constraint then allows only ``agent`` and
``owner``. The downgrade restores the wider CHECK and keeps the rows as the owner's, so
no pause becomes one an agent could lift.
"""

from alembic import op

revision = "0155_owner_message_pauses_are_owners"
down_revision = "0173_reach_me_without_activity"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        "UPDATE ln_supervision_holds SET source_message_id = NULL"
        " WHERE source = 'owner' AND source_message_id IS NOT NULL"
    )
    op.execute("UPDATE ln_supervision_holds SET source = 'owner' WHERE source = 'owner_message'")
    op.drop_constraint("ln_supervision_hold_source", "ln_supervision_holds", type_="check")
    op.create_check_constraint(
        "ln_supervision_hold_source", "ln_supervision_holds", "source IN ('agent','owner')"
    )


def downgrade() -> None:
    op.drop_constraint("ln_supervision_hold_source", "ln_supervision_holds", type_="check")
    op.create_check_constraint(
        "ln_supervision_hold_source",
        "ln_supervision_holds",
        "source IN ('agent','owner_message','owner')",
    )
