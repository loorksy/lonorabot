"""Add global model provider and model selection.

Revision ID: 0003_model
Revises: 0002_auth
Create Date: 2026-10-12
"""

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op

revision: str = "0003_model"
down_revision: str | None = "0002_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "global_model_settings",
        sa.Column("id", sa.Integer(), nullable=False),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=200), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("id = 1", name="global_model_settings_singleton_check"),
        sa.CheckConstraint(
            "provider IN ('xai', 'openai', 'anthropic', 'deepseek', 'zai', 'openrouter')",
            name="global_model_settings_provider_check",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.execute(
        "INSERT INTO global_model_settings (id, provider, model_name, updated_at) "
        "VALUES (1, 'xai', 'grok-4.20-0309-non-reasoning', CURRENT_TIMESTAMP)"
    )


def downgrade() -> None:
    op.drop_table("global_model_settings")
