"""Join main's chain and the stacked W-AUTH/W-PAUSE chain into one head (no schema change).

This branch is stacked on unmerged branches whose migrations (0061, 0155) are not yet on
main's chain (0176). The lead re-chains them at merge; this revision then goes away.
"""

revision = "0126_team_heads_merge"
down_revision = ("0176_weekly_reports", "0155_owner_message_pauses_are_owners")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
