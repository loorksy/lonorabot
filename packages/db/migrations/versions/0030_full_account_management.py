"""Explicit non-expiring account management, preserving existing signed grants."""

import sqlalchemy as sa
from alembic import op

revision = "0030_full_account_management"
down_revision = "0029_account_authority"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.alter_column(
        "ln_account_authorities",
        "valid_until",
        existing_type=sa.DateTime(timezone=True),
        nullable=True,
    )


def downgrade() -> None:
    # Do not invent an expiry or rewrite a signed envelope on downgrade. An
    # operator must explicitly remove non-expiring grants before dropping support.
    connection = op.get_bind()
    if connection.execute(
        sa.text("SELECT count(*) FROM ln_account_authorities WHERE valid_until IS NULL")
    ).scalar():
        raise RuntimeError("non_expiring_authorities_require_explicit_removal")
    op.alter_column(
        "ln_account_authorities",
        "valid_until",
        existing_type=sa.DateTime(timezone=True),
        nullable=False,
    )
