"""Phones registered for push (VISION 11.4).

One row per device, bound to the sign-in session that registered it (signing out deletes it),
with the Expo push token encrypted and its SHA-256 unique. No backfill: no phone was ever
registered. The downgrade drops the table.
"""

import sqlalchemy as sa
from alembic import op

revision = "0140_push_devices"
down_revision = "0058_skill_versions"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "ln_push_devices",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("device_id", sa.String(length=64), nullable=False),
        sa.Column("session_hash", sa.String(length=64), nullable=False),
        sa.Column("platform", sa.String(length=16), nullable=False),
        sa.Column("token_hash", sa.String(length=64), nullable=False),
        sa.Column("token_ciphertext", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["ln_owners.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["session_hash"], ["ln_sessions.token_hash"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "device_id", name="uq_push_device"),
        sa.UniqueConstraint("token_hash"),
    )
    op.create_index("ix_ln_push_devices_owner_id", "ln_push_devices", ["owner_id"])
    op.create_index("ix_ln_push_devices_session_hash", "ln_push_devices", ["session_hash"])


def downgrade() -> None:
    op.drop_table("ln_push_devices")
