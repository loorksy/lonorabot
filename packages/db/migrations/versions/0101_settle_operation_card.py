"""The resolve_operation card becomes Settle Uncertain Operation (mandate 10.3, 10.3.2).

Stored owner-action rows of kind ``resolve_operation`` become ``settle_operation``
(14.3.9: the card contract's kind literal changes). The payload hash covers the kind, so
it is recomputed with the new kind: a later proposal for the same operation finds the
stored pending card instead of raising a second one. Payloads, results and statuses are
unchanged; the journal rows the cards name are not touched.
"""

import json

import sqlalchemy as sa
from alembic import op
from lonora_session.idempotency import request_hash

revision = "0101_settle_operation_card"
down_revision = "0100_execution_receipts"
branch_labels = None
depends_on = None


def rename(old: str, new: str) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text("SELECT id, payload FROM ln_owner_actions WHERE kind = :old"), {"old": old}
    ).all()
    for identifier, payload in rows:
        value = json.loads(payload) if isinstance(payload, str) else payload
        bind.execute(
            sa.text("UPDATE ln_owner_actions SET kind = :new, payload_hash = :hash WHERE id = :id"),
            {"new": new, "hash": request_hash({"kind": new, "payload": value}), "id": identifier},
        )


def upgrade() -> None:
    rename("resolve_operation", "settle_operation")


def downgrade() -> None:
    rename("settle_operation", "resolve_operation")
