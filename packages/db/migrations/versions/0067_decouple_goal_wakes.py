"""Watches and routines no longer belong to trading goals (mandate 14.3.14, 14.3.9).

Trading goals are removed (mandate 14.2.4); their watches and routines are decoupled
first. A stored ``Watch`` payload is validated by a contract with ``extra="forbid"``, so
its ``goal_id``, ``step_id`` and ``goal_plan_version`` keys are stripped before the
contract drops them. A watch or routine that was armed for a goal step only carried that
step's plan: it is switched off (a watch keeps the ``watch_cancelled`` code the app
already shows) and stays as history. The routine columns ``goal_id`` and ``step_id``
are dropped.

The downgrade restores the two empty columns; the stripped payload keys and the
switched-off state are not restored.
"""

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0067_decouple_goal_wakes"
down_revision = "0050_genui_state_and_origin"
branch_labels = None
depends_on = None

GOAL_KEYS = ("goal_id", "step_id", "goal_plan_version")


def _loaded(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return json.loads(value)
    return dict(value or {})


def upgrade() -> None:
    connection = op.get_bind()
    watches = connection.execute(
        sa.text(
            "SELECT id, payload, state FROM ln_market_watches"
            " WHERE payload::jsonb ?| array['goal_id', 'step_id', 'goal_plan_version']"
        )
    ).all()
    for identifier, raw_payload, raw_state in watches:
        payload = _loaded(raw_payload)
        state = _loaded(raw_state)
        linked = bool(payload.get("goal_id"))
        payload = {key: value for key, value in payload.items() if key not in GOAL_KEYS}
        if linked:
            payload["enabled"] = False
            state = {
                key: value
                for key, value in state.items()
                if key not in {"evaluation_status", "next_check"}
            }
            state["code"] = "watch_cancelled"
        connection.execute(
            sa.text(
                "UPDATE ln_market_watches SET payload = CAST(:payload AS json),"
                " state = CAST(:state AS json), version = version + 1 WHERE id = :id"
            ),
            {"id": identifier, "payload": json.dumps(payload), "state": json.dumps(state)},
        )
    connection.execute(sa.text("UPDATE ln_routines SET enabled = false WHERE goal_id IS NOT NULL"))
    op.drop_column("ln_routines", "step_id")
    op.drop_column("ln_routines", "goal_id")


def downgrade() -> None:
    op.add_column(
        "ln_routines",
        sa.Column(
            "goal_id", sa.String(36), sa.ForeignKey("ln_trading_goals.id", ondelete="CASCADE")
        ),
    )
    op.add_column("ln_routines", sa.Column("step_id", sa.String(64)))
