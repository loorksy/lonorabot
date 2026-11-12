"""A skill's versions outlive the skill (mandate 5.5.5: revert to any version).

Deleting a skill used to cascade to ``ln_skill_versions`` and erase its history, so a
deleted skill could not be brought back. The versions now keep their own ``agent_id``
(copied from the skill) and no longer depend on the skill row; they are removed with
the agent or the owner. Each version also records whether it came from a workspace or
GitHub package (``package``), which only the package lifecycle may restore.

The downgrade drops the versions of skills that no longer exist, restores the cascade
and drops ``agent_id``.
"""

import sqlalchemy as sa
from alembic import op

revision = "0120_skill_versions_outlive_skill"
down_revision = "0131_agent_model_owner_only"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ln_skill_versions", sa.Column("agent_id", sa.String(length=36)))
    op.add_column(
        "ln_skill_versions",
        sa.Column("package", sa.Boolean(), nullable=False, server_default=sa.false()),
    )
    op.execute(
        "UPDATE ln_skill_versions AS v SET agent_id = s.agent_id, "
        "package = (s.state::jsonb ? 'package') "
        "FROM ln_skills AS s WHERE s.id = v.skill_id"
    )
    op.create_foreign_key(
        "ln_skill_versions_agent_id_fkey",
        "ln_skill_versions",
        "ln_agents",
        ["agent_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("ln_skill_versions_skill_id_fkey", "ln_skill_versions", type_="foreignkey")
    op.create_index(
        "ix_ln_skill_versions_agent", "ln_skill_versions", ["owner_id", "agent_id", "skill_id"]
    )


def downgrade() -> None:
    op.drop_index("ix_ln_skill_versions_agent", table_name="ln_skill_versions")
    op.execute(
        "DELETE FROM ln_skill_versions AS v "
        "WHERE NOT EXISTS (SELECT 1 FROM ln_skills AS s WHERE s.id = v.skill_id)"
    )
    op.create_foreign_key(
        "ln_skill_versions_skill_id_fkey",
        "ln_skill_versions",
        "ln_skills",
        ["skill_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.drop_constraint("ln_skill_versions_agent_id_fkey", "ln_skill_versions", type_="foreignkey")
    op.drop_column("ln_skill_versions", "package")
    op.drop_column("ln_skill_versions", "agent_id")
