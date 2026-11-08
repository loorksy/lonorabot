"""Supervision grants and the pauses supervisors put on other agents' work.

The data step gives each owner's Personal Agent a ``default`` grant over every other
agent of that owner, so Lonora reads and steers every agent from the start; the owner
revokes any grant with one tap. Seeding skips pairs that already have an active grant,
so running it again adds nothing. The downgrade drops both tables.
"""

import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0041_supervision_grants"
down_revision = "0039_owner_profile_memory_revisions"
branch_labels = None
depends_on = None


def seed_default_grants(connection: Any) -> int:
    """One active default grant from each Personal Agent over every other agent."""
    now = datetime.now(UTC)
    pairs = connection.execute(
        sa.text(
            "SELECT p.owner_id, p.id, a.id FROM ln_agents p JOIN ln_agents a "
            "ON a.owner_id = p.owner_id AND a.id <> p.id WHERE p.role = 'personal' "
            "AND NOT EXISTS (SELECT 1 FROM ln_supervision_grants g WHERE "
            "g.supervisor_agent_id = p.id AND g.supervised_agent_id = a.id "
            "AND g.revoked_at IS NULL) ORDER BY p.owner_id, a.created_at, a.id"
        )
    ).all()
    for owner_id, personal_id, agent_id in pairs:
        connection.execute(
            sa.text(
                "INSERT INTO ln_supervision_grants (id, owner_id, supervisor_agent_id, "
                "supervised_agent_id, created_via, created_at) VALUES (:id, :owner, "
                ":supervisor, :supervised, 'default', :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "owner": owner_id,
                "supervisor": personal_id,
                "supervised": agent_id,
                "now": now,
            },
        )
    return len(pairs)


def upgrade() -> None:
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
    op.create_table(
        "ln_supervision_holds",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "holder_agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column(
            "agent_id",
            sa.String(36),
            sa.ForeignKey("ln_agents.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("target_kind", sa.String(8), nullable=False),
        sa.Column("target_id", sa.String(36), nullable=False),
        sa.Column("source", sa.String(16), nullable=False),
        sa.Column(
            "source_message_id",
            sa.String(36),
            sa.ForeignKey("ln_messages.id", ondelete="SET NULL"),
        ),
        sa.Column("source_run_id", sa.String(36)),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("released_at", sa.DateTime(timezone=True)),
        sa.Column("released_by", sa.String(8)),
        sa.CheckConstraint(
            "target_kind IN ('agent','task','routine','watch')",
            name="ln_supervision_hold_target_kind",
        ),
        sa.CheckConstraint(
            "source IN ('agent','owner_message')", name="ln_supervision_hold_source"
        ),
        sa.CheckConstraint(
            "released_by IS NULL OR released_by IN ('holder','owner','stale')",
            name="ln_supervision_hold_released_by",
        ),
    )
    op.create_index(
        "ln_supervision_hold_agent",
        "ln_supervision_holds",
        ["owner_id", "agent_id", "released_at"],
    )
    op.create_index(
        "ln_supervision_hold_holder",
        "ln_supervision_holds",
        ["owner_id", "holder_agent_id", "released_at"],
    )
    op.create_index(
        "ln_supervision_hold_live_target",
        "ln_supervision_holds",
        ["target_kind", "target_id"],
        unique=True,
        postgresql_where=sa.text("released_at IS NULL"),
    )
    seed_default_grants(op.get_bind())


def downgrade() -> None:
    op.drop_index("ln_supervision_hold_live_target", table_name="ln_supervision_holds")
    op.drop_index("ln_supervision_hold_holder", table_name="ln_supervision_holds")
    op.drop_index("ln_supervision_hold_agent", table_name="ln_supervision_holds")
    op.drop_table("ln_supervision_holds")
    op.drop_index("ln_supervision_grant_active_pair", table_name="ln_supervision_grants")
    op.drop_index("ln_supervision_grant_supervised", table_name="ln_supervision_grants")
    op.drop_index("ln_supervision_grant_supervisor", table_name="ln_supervision_grants")
    op.drop_table("ln_supervision_grants")
