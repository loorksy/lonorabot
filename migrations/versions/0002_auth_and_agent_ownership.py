"""Add local-owner authentication and agent ownership.

Revision ID: 0002_auth
Revises: 0001_initial
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0002_auth"
down_revision: str | None = "0001_initial"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "users",
        sa.Column("id", postgresql.UUID(as_uuid=True), nullable=False),
        sa.Column("email", sa.String(length=254), nullable=False),
        sa.Column("password_hash", sa.String(length=512), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("email", name="users_email_key"),
    )
    op.add_column("agents", sa.Column("owner_id", postgresql.UUID(as_uuid=True), nullable=True))
    op.create_foreign_key(
        "agents_owner_id_fkey", "agents", "users", ["owner_id"], ["id"], ondelete="CASCADE"
    )
    op.create_index("agents_owner_created_idx", "agents", ["owner_id", "created_at"])


def downgrade() -> None:
    op.drop_index("agents_owner_created_idx", table_name="agents")
    op.drop_constraint("agents_owner_id_fkey", "agents", type_="foreignkey")
    op.drop_column("agents", "owner_id")
    op.drop_table("users")
