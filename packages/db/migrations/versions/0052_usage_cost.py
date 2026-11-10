"""Usage dashboard: an index on ``ln_usage (owner_id, created_at)``.

Usage stays a resource payload (``TokenUsage`` plus provider and model); cost is priced
at read time from the server-side list in ``lonora_core.model_pricing``, so no column is
added and old rows are priced the same way as new ones. The dashboard reads windows of
one owner's rows by time (``/usage/series``, ``/usage/rank``, ``/usage/export.csv``),
which this index serves.
"""

from alembic import op

revision = "0052_usage_cost"
down_revision = "0051_owner_identity_and_delivery"
branch_labels = None
depends_on = None

INDEX = "ln_usage_owner_created"


def upgrade() -> None:
    op.create_index(INDEX, "ln_usage", ["owner_id", "created_at"])


def downgrade() -> None:
    op.drop_index(INDEX, table_name="ln_usage")
