"""Secret values given to workspace commands, encrypted, so the scan of workspace output
still covers a rotated or deleted value a log or a running process may hold (7.2.6)."""

import sqlalchemy as sa
from alembic import op

revision = "0135_workspace_given"
down_revision = "0070_secret_scopes"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_workspace_given",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column(
            "owner_id",
            sa.String(36),
            sa.ForeignKey("ln_owners.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("name", sa.String(80), nullable=False),
        sa.Column("digest", sa.String(64), nullable=False),
        sa.Column("ciphertext", sa.Text(), nullable=False),
        sa.Column("given_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("owner_id", "digest", name="ln_workspace_given_digest"),
    )
    op.create_index("ix_ln_workspace_given_owner_id", "ln_workspace_given", ["owner_id"])


def downgrade() -> None:
    op.drop_table("ln_workspace_given")
