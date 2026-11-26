"""Lonora's fixed model list (VISION 12.4, Amendment 4): the stored provider lists go.

A fixed provider's models are the list the release ships (``lonora_providers/models.json``),
so the ``catalog:<provider>`` settings that reading a provider's models once wrote are
deleted. The owner's own endpoint keeps ``catalog:openai_compatible``: its models are the
owner's, read from it. The downgrade restores nothing: the list is in the code, and the
earlier release reads a missing catalog as an empty one until its provider is read again.
"""

import sqlalchemy as sa
from alembic import op

revision = "0201_fixed_model_list"
down_revision = "0130_routine_skipped_occurrences"
branch_labels = None
depends_on = None

# The providers whose models are the shipped list (every provider but the owner's endpoint).
FIXED = ("openai", "anthropic", "deepseek", "zai", "openrouter")


def upgrade() -> None:
    settings = sa.table("ln_settings", sa.column("key", sa.String()))
    op.get_bind().execute(
        sa.delete(settings).where(settings.c.key.in_(["catalog:" + name for name in FIXED]))
    )


def downgrade() -> None:
    pass
