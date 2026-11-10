"""Card lifetimes: the newer card that replaced one, owner-drafted cards, approval expiry.

``ln_owner_actions.superseded_by`` names the card that replaced an older one of the same
subject («عرض الأحدث»). ``source`` gains ``owner``: a grant card the owner drafted from
the composer's mandate sheet (it still signs only with the passkey). Trade approvals
gain ``expires_at`` (nullable: older rows never expire); a pending approval past it is
settled as expired when next read or decided. The downgrade drops both columns and
files owner-drafted cards under ``system``.
"""

import sqlalchemy as sa
from alembic import op

revision = "0048_card_lifetimes"
down_revision = "0045_chat_lists"  # LOCAL-ONLY; final: 0047_conversation_anchors
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ln_owner_actions", sa.Column("superseded_by", sa.String(36), nullable=True))
    op.drop_constraint("ln_owner_action_source", "ln_owner_actions", type_="check")
    op.create_check_constraint(
        "ln_owner_action_source", "ln_owner_actions", "source IN ('agent','system','owner')"
    )
    op.add_column(
        "ln_trade_approvals",
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("ln_trade_approvals", "expires_at")
    op.execute("UPDATE ln_owner_actions SET source = 'system' WHERE source = 'owner'")
    op.drop_constraint("ln_owner_action_source", "ln_owner_actions", type_="check")
    op.create_check_constraint(
        "ln_owner_action_source", "ln_owner_actions", "source IN ('agent','system')"
    )
    op.drop_column("ln_owner_actions", "superseded_by")
