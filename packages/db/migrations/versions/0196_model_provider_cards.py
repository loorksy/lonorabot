"""A Secret card connects a model provider (Q14 (b), VISION.md 7.2, 12.1).

Nothing is stored differently on upgrade: the card is a ``secret`` row whose ``connect``
is ``model_provider``. The downgrade refuses while such a card exists: 0071's downgrade
would turn it into a ``connect_credential`` row whose target the earlier contracts
refuse. Remove those cards first. The key and its router record stay readable rows.
"""

import sqlalchemy as sa
from alembic import op

revision = "0196_model_provider_cards"
down_revision = "0100_execution_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    cards = (
        op.get_bind()
        .execute(
            sa.text(
                "SELECT count(*) FROM ln_owner_actions"
                " WHERE kind = 'secret' AND payload->>'connect' = 'model_provider'"
            )
        )
        .scalar_one()
    )
    if cards:
        raise RuntimeError(
            f"{cards} Secret card(s) connect a model provider, which the earlier release "
            "cannot read: remove them first"
        )
