"""An opportunity keeps every unsettled operation that names it (mandate 14.2.5).

The entry-thesis gate allowed one pending entry and one pending management operation per
thesis, so it stored them as ``pending_entry_operation_id`` and
``pending_management_operation_id``. Opportunities are now agent memory and never refuse
an operation, so several may be open at once: they are stored as one list,
``pending_operation_ids``. Each stored opportunity's two keys become that list.

The downgrade splits the list back by each operation's journal action (the last one of
each kind is kept, as the two keys can hold only one each).
"""

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0085_opportunity_pending_operations"
down_revision = "0068_end_trading_goals"
branch_labels = None
depends_on = None

OLD = ("pending_entry_operation_id", "pending_management_operation_id")
NEW = "pending_operation_ids"
ENTRY_ACTIONS = {"buy", "sell", "buy_limit", "sell_limit", "buy_stop", "sell_stop"}


def _loaded(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        return json.loads(value)
    return dict(value or {})


def _store(connection: Any, identifier: str, state: dict[str, Any]) -> None:
    connection.execute(
        sa.text("UPDATE ln_trading_opportunities SET state = CAST(:state AS json) WHERE id = :id"),
        {"id": identifier, "state": json.dumps(state)},
    )


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, state FROM ln_trading_opportunities"
            " WHERE state::jsonb ?| array['pending_entry_operation_id',"
            " 'pending_management_operation_id']"
        )
    ).all()
    for identifier, raw in rows:
        state = _loaded(raw)
        pending = [state[key] for key in OLD if state.get(key)]
        state = {key: value for key, value in state.items() if key not in OLD}
        _store(connection, identifier, {**state, NEW: pending})


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT id, state FROM ln_trading_opportunities"
            " WHERE state::jsonb ? 'pending_operation_ids'"
        )
    ).all()
    for identifier, raw in rows:
        state = _loaded(raw)
        restored: dict[str, Any] = dict.fromkeys(OLD)
        for operation_id in state.pop(NEW, None) or []:
            request = connection.scalar(
                sa.text("SELECT request FROM ln_trading_journal WHERE operation_id = :o"),
                {"o": operation_id},
            )
            action = _loaded(request).get("action") if request is not None else None
            restored[OLD[0] if action in ENTRY_ACTIONS else OLD[1]] = operation_id
        _store(connection, identifier, {**state, **restored})
