"""Broker health attention items carry their problem (mandate 9.4).

The single ``broker_degraded`` item and the ``broker_recovered`` item are replaced by
one item per account and problem: ``broker_token_rejected``,
``broker_account_undeployed`` and ``broker_connection_lost``, raised from the account's
stored recovery state. A stored ``broker_degraded`` row named no problem, so it becomes
``broker_connection_lost`` (the generic one), and an open one is withdrawn: the gateway
raises the current problem of each account again under its own code on its next tick.
A ``broker_recovered`` row only said that a degraded state ended; it is deleted, as the
projection keeps its source events and effect receipts. The downgrade restores the
codes; the rows deleted here are not recreated.
"""

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0170_broker_health_attention"
down_revision = "0050_genui_state_and_origin"
branch_labels = None
depends_on = None


def parameters(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return dict(value or {})


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, status, version, parameters FROM ln_attention "
            "WHERE code = 'broker_degraded' ORDER BY id"
        )
    ).all()
    for identifier, status, version, stored in rows:
        values = parameters(stored)
        if status in {"pending", "ready"}:
            status, version = "suppressed", version + 1
            values["suppression_code"] = "attention_superseded_state"
        connection.execute(
            sa.text(
                "UPDATE ln_attention SET code = 'broker_connection_lost', status = :status, "
                "version = :version, parameters = CAST(:parameters AS JSON) WHERE id = :id"
            ),
            {
                "id": identifier,
                "status": status,
                "version": version,
                "parameters": json.dumps(values),
            },
        )
    connection.execute(sa.text("DELETE FROM ln_attention WHERE code = 'broker_recovered'"))


def downgrade() -> None:
    op.get_bind().execute(
        sa.text(
            "UPDATE ln_attention SET code = 'broker_degraded' WHERE code IN "
            "('broker_token_rejected', 'broker_account_undeployed', 'broker_connection_lost')"
        )
    )
