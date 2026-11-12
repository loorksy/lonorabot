"""Join W-ENV's secret-card chain and main's chain into one head (no schema change).

The lead re-chains migrations at merge; this revision only lets the stacked branch
upgrade to a single head meanwhile.
"""

revision = "0195_models_merge_heads"
down_revision = ("0071_secret_card_kinds", "0085_opportunity_pending_operations")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
