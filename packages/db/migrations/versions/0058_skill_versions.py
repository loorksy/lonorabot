"""Skill version history: one row per saved version of an installed skill.

Every create, update and restore of a skill writes its validated payload under the
skill's resource ``version``; «سجل الإصدارات» lists them and «الرجوع إلى الإصدار N»
saves an older payload as a new version. Existing skills get their current payload as
their first history row. The downgrade drops the history; the skills stay as they are.
"""

import sqlalchemy as sa
from alembic import op

revision = "0058_skill_versions"
down_revision = "0057_agent_goals_knowledge_links"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_skill_versions",
        sa.Column("skill_id", sa.String(length=36), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("payload", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["ln_skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["owner_id"], ["ln_owners.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("skill_id", "version"),
    )
    op.execute(
        sa.text(
            "INSERT INTO ln_skill_versions (skill_id, version, owner_id, payload, created_at) "
            "SELECT id, version, owner_id, payload, updated_at FROM ln_skills"
        )
    )


def downgrade() -> None:
    op.drop_table("ln_skill_versions")
