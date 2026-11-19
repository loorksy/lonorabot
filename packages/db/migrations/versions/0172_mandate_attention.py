"""The Mandate card's attention item (``mandate_proposed``).

The code needs no stored change on the way up. The earlier code does not know it, so
the downgrade deletes its rows; deleted rows are not recreated.
"""

import sqlalchemy as sa
from alembic import op

revision = "0172_mandate_attention"
down_revision = "0100_execution_receipts"
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    op.get_bind().execute(sa.text("DELETE FROM ln_attention WHERE code = 'mandate_proposed'"))
