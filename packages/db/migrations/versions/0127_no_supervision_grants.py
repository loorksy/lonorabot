"""Supervision grants are deleted (mandate 3.3.3, 14.2.6): only Lonora leads, by its role.

The upgrade deletes the owner-action cards of the three grant kinds (``supervise``,
``supervision_created``, ``supervision_stopped``; 14.3.9: a stored row of a removed kind
is migrated, never left for a client that no longer renders it) and drops
``ln_supervision_grants``. Pause holds (``ln_supervision_holds``) and their
``supervision_paused`` cards stay: they record pauses, not grants.

The downgrade recreates the table empty: no grant comes back, so no agent regains
another's reads or control.
"""

import sqlalchemy as sa
from alembic import op

revision = "0127_no_supervision_grants"
down_revision = "0126_team_heads_merge"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.execute(
        sa.text(
            "DELETE FROM ln_owner_actions"
            " WHERE kind IN ('supervise', 'supervision_created', 'supervision_stopped')"
        )
    )
    op.drop_table("ln_supervision_grants")


def downgrade() -> None:
    op.create_table(
        "ln_supervision_grants",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "supervisor_agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "supervised_agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("created_via", sa.String(16), nullable=False),
        sa.Column(
            "source_message_id",
            sa.String(36),
            sa.ForeignKey("ln_messages.id", ondelete="SET NULL"),
        ),
        sa.Column("created_by_agent_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("revoked_at", sa.DateTime(timezone=True)),
        sa.Column("revoked_via", sa.String(16)),
        sa.CheckConstraint(
            "created_via IN ('default','owner_ui','owner_message','owner_card')",
            name="ln_supervision_grant_created_via",
        ),
        sa.CheckConstraint(
            "revoked_via IS NULL OR revoked_via IN ('owner_ui','owner_card','owner_message')",
            name="ln_supervision_grant_revoked_via",
        ),
        sa.CheckConstraint(
            "supervisor_agent_id <> supervised_agent_id", name="ln_supervision_grant_distinct"
        ),
    )
    op.create_index(
        "ln_supervision_grant_supervisor",
        "ln_supervision_grants",
        ["owner_id", "supervisor_agent_id", "revoked_at"],
    )
    op.create_index(
        "ln_supervision_grant_supervised",
        "ln_supervision_grants",
        ["owner_id", "supervised_agent_id", "revoked_at"],
    )
    op.create_index(
        "ln_supervision_grant_active_pair",
        "ln_supervision_grants",
        ["supervisor_agent_id", "supervised_agent_id"],
        unique=True,
        postgresql_where=sa.text("revoked_at IS NULL"),
    )
