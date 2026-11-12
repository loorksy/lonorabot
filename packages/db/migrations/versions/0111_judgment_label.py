"""The agent's judgment label (mandate 5.5.3, 14.3.9).

The label is stored beside the request like the reason and tolerance: in the journal's
``annotation`` (a JSON object, so no column), on Trade Approval rows (``label``) and on
the closed-trade row that copies its opening order's label (``label``). No stored
request, fingerprint or operation id changes: an unresolved journal row reconciles after
this migration exactly as before. Stored annotations without a label stay valid (the
field is optional). The downgrade drops the two columns.
"""

import sqlalchemy as sa
from alembic import op

revision = "0111_judgment_label"
down_revision = "0110_closed_trades"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("ln_trade_approvals", sa.Column("label", sa.String(40)))
    op.add_column("ln_closed_trades", sa.Column("label", sa.String(40)))


def downgrade() -> None:
    op.drop_column("ln_closed_trades", "label")
    op.drop_column("ln_trade_approvals", "label")
