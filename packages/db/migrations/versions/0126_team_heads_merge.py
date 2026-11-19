"""Join the stacked chains into one head (no schema change).

This branch stacks #138 (0125, on main's 0176 and W-AUTH's 0061) and #146, whose W-PAUSE
base adds 0155 on 0061. The lead re-chains them at merge; this revision then goes away.
"""

revision = "0126_team_heads_merge"
down_revision = ("0125_flat_team_creation", "0155_owner_message_pauses_are_owners")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
