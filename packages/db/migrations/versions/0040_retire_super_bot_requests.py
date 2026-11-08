"""Retire Super Bot requests and goal autonomy (data only, plus one allowed status).

A signed AccountAuthority is the only grant. Super Bot requests that were still pending
or activated get status 'retired'; every row stays as audit history and nothing is
deleted. Open "Super Bot needs authorization" inbox items are withdrawn ('suppressed').

Goals are plans under the agent's grant: the retired goal autonomy keys
('autonomous', 'super_bot_request_id') are removed from every goal's state, so no read of
an older goal tells the model it trades autonomously.

The readiness review after signing is now keyed on grants. Grants already active here
were signed before that review existed, so each gets a "skipped" review receipt and no
agent is woken for an old grant.

Every change is recorded in a marker row, and the downgrade restores exactly those rows:
the previous request statuses, the inbox items, the goal keys and the receipts this step
added.
"""

import json
from datetime import UTC, datetime
from typing import Any, cast

import sqlalchemy as sa
from alembic import op

revision = "0040_retire_super_bot_requests"
down_revision = "0040_explicit_agent_permission_rows"
branch_labels = None
depends_on = None

MARKER = "migration:0040_retire_super_bot_requests"
STATUSES = "'pending','activated','rejected','expired','cancelled','paused','disabled'"
SKIPPED = {"skipped": "granted_before_review"}
GOAL_KEYS = ("autonomous", "super_bot_request_id")


def payload_of(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def upgrade() -> None:
    connection = op.get_bind()
    op.drop_constraint("ln_super_bot_status", "ln_super_bot_requests", type_="check")
    op.create_check_constraint(
        "ln_super_bot_status", "ln_super_bot_requests", f"status IN ({STATUSES},'retired')"
    )
    marker = payload_of(
        connection.execute(
            sa.text("SELECT payload FROM ln_settings WHERE key = :key"), {"key": MARKER}
        ).scalar()
    )
    requests: dict[str, str] = dict(marker.get("requests", {}))
    attention: dict[str, str] = dict(marker.get("attention", {}))
    receipts: list[str] = list(marker.get("receipts", []))
    goals: dict[str, dict[str, Any]] = dict(marker.get("goals", {}))
    now = datetime.now(UTC)
    for identifier, status in connection.execute(
        sa.text(
            "SELECT id, status FROM ln_super_bot_requests "
            "WHERE status IN ('pending','activated') ORDER BY id"
        )
    ):
        requests[str(identifier)] = str(status)
        connection.execute(
            sa.text(
                "UPDATE ln_super_bot_requests SET status='retired', updated_at=:now WHERE id=:id"
            ),
            {"id": identifier, "now": now},
        )
    for identifier, status in connection.execute(
        sa.text(
            "SELECT id, status FROM ln_attention WHERE code='super_bot_authorization' "
            "AND status IN ('pending','ready') ORDER BY id"
        )
    ):
        attention[str(identifier)] = str(status)
        connection.execute(
            sa.text("UPDATE ln_attention SET status='suppressed', updated_at=:now WHERE id=:id"),
            {"id": identifier, "now": now},
        )
    for identifier, value in connection.execute(
        sa.text(
            "SELECT id, state FROM ln_trading_goals WHERE "
            + " OR ".join(f"(state::jsonb -> '{key}') IS NOT NULL" for key in GOAL_KEYS)
            + " ORDER BY id"
        )
    ):
        state = payload_of(value)
        goals[str(identifier)] = {
            **goals.get(str(identifier), {}),
            **{key: state.pop(key) for key in GOAL_KEYS if key in state},
        }
        # Data cleanup only: the goal's version is unchanged, so no client sees a conflict.
        connection.execute(
            sa.text("UPDATE ln_trading_goals SET state = CAST(:state AS json) WHERE id=:id"),
            {"id": identifier, "state": json.dumps(state)},
        )
    receipt_table = sa.table(
        "ln_effect_receipts",
        sa.column("key", sa.String),
        sa.column("result", sa.JSON),
        sa.column("created_at", sa.DateTime(timezone=True)),
    )
    new_receipts: list[dict[str, Any]] = []
    for (identifier,) in connection.execute(
        sa.text(
            "SELECT a.id FROM ln_account_authorities a WHERE a.status='active' AND NOT EXISTS "
            "(SELECT 1 FROM ln_effect_receipts r WHERE r.key = 'activation-review:' || a.id) "
            "ORDER BY a.id"
        )
    ):
        key = "activation-review:" + str(identifier)
        new_receipts.append({"key": key, "result": SKIPPED, "created_at": now})
        receipts.append(key)
    if new_receipts:
        op.bulk_insert(receipt_table, new_receipts)
    payload = {
        "requests": requests,
        "attention": attention,
        "goals": goals,
        "receipts": sorted(set(receipts)),
    }
    settings = sa.table(
        "ln_settings",
        sa.column("key", sa.String),
        sa.column("payload", sa.JSON),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    if marker:
        connection.execute(
            settings.update()
            .where(settings.c.key == MARKER)
            .values(payload=payload, updated_at=now)
        )
    else:
        op.bulk_insert(settings, [{"key": MARKER, "payload": payload, "updated_at": now}])


def downgrade() -> None:
    connection = op.get_bind()
    marker = payload_of(
        connection.execute(
            sa.text("SELECT payload FROM ln_settings WHERE key = :key"), {"key": MARKER}
        ).scalar()
    )
    now = datetime.now(UTC)
    for identifier, status in dict(marker.get("requests", {})).items():
        connection.execute(
            sa.text(
                "UPDATE ln_super_bot_requests SET status=:status, updated_at=:now "
                "WHERE id=:id AND status='retired'"
            ),
            {"id": identifier, "status": status, "now": now},
        )
    # A row retired some other way (none are) still needs an allowed status to downgrade.
    connection.execute(
        sa.text("UPDATE ln_super_bot_requests SET status='disabled' WHERE status='retired'")
    )
    for identifier, status in dict(marker.get("attention", {})).items():
        connection.execute(
            sa.text(
                "UPDATE ln_attention SET status=:status, updated_at=:now "
                "WHERE id=:id AND status='suppressed'"
            ),
            {"id": identifier, "status": status, "now": now},
        )
    for identifier, keys in dict(marker.get("goals", {})).items():
        current = connection.execute(
            sa.text("SELECT state FROM ln_trading_goals WHERE id=:id"), {"id": identifier}
        ).scalar()
        if current is None:
            continue
        connection.execute(
            sa.text("UPDATE ln_trading_goals SET state = CAST(:state AS json) WHERE id=:id"),
            {"id": identifier, "state": json.dumps({**payload_of(current), **dict(keys)})},
        )
    for key in marker.get("receipts", []):
        connection.execute(
            sa.text("DELETE FROM ln_effect_receipts WHERE key=:key AND result->>'skipped'=:code"),
            {"key": key, "code": SKIPPED["skipped"]},
        )
    connection.execute(sa.text("DELETE FROM ln_settings WHERE key = :key"), {"key": MARKER})
    op.drop_constraint("ln_super_bot_status", "ln_super_bot_requests", type_="check")
    op.create_check_constraint(
        "ln_super_bot_status", "ln_super_bot_requests", f"status IN ({STATUSES})"
    )
