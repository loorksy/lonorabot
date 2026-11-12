"""Only the owner assigns an agent's model (VISION 12.3, lead decision Q20 (a)).

The Automatic / Fixed modes, the owner's allowed list and the two model cards go:

- Every stored model record (``ln_settings`` key ``agent-model:*``) loses ``mode``, and
  its ``previous`` ``{mode, preference}`` becomes that preference alone. A choice an
  agent made of its own accord (``chosen_by`` ``agent`` with no owner message on its
  ``agent.model.updated`` event) keeps its model but reads as nobody's (``chosen_by``
  none); one an agent applied on the owner's message reads as the owner's. The contract
  is extra="forbid", so this runs before any reader sees the new shape.
- The owner's allowed list (``model_allowed``) is removed: nothing reads it any more.
- Model cards (``agent_model``, ``agent_model_changed``): a pending one is settled as
  ``superseded`` (``model_cards_removed``), then every one moves to
  ``ln_owner_actions_model_retired``, which nothing reads, so no card list meets a kind
  the clients no longer render. Nothing is erased.

Every original record and the allowed list are kept in a marker row. The downgrade puts
them back: the marker's records and allowed list, records written later in the old shape,
and the retired cards (settled ones stay settled: a downgrade never reopens a card).
"""

import json
from datetime import UTC, datetime
from typing import Any, cast

import sqlalchemy as sa
from alembic import op

revision = "0131_agent_model_owner_only"
down_revision = "0090_routine_work_threads"
branch_labels = None
depends_on = None

MARKER = "migration:0131_agent_model_owner_only"
ALLOWED_KEY = "model_allowed"
KINDS = "('agent_model','agent_model_changed')"
RETIRED = "ln_owner_actions_model_retired"


def payload_of(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def owner_named(connection: sa.Connection, record: dict[str, Any]) -> bool:
    """Whether the event of the record's current revision answered an owner message."""
    payload = connection.execute(
        sa.text(
            "SELECT payload FROM ln_events WHERE owner_id = :owner AND agent_id = :agent"
            " AND kind = 'agent.model.updated' AND payload ->> 'revision' = :revision"
            " ORDER BY cursor DESC LIMIT 1"
        ),
        {
            "owner": record.get("owner_id"),
            "agent": record.get("agent_id"),
            "revision": str(record.get("revision")),
        },
    ).scalar()
    return bool(payload_of(payload).get("source_message_id"))


def put(connection: sa.Connection, key: str, payload: dict[str, Any], now: datetime) -> None:
    connection.execute(
        sa.text("UPDATE ln_settings SET payload = :payload, updated_at = :now WHERE key = :key"),
        {"key": key, "payload": json.dumps(payload), "now": now},
    )


def upgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)
    records: dict[str, dict[str, Any]] = {}
    for key, value in connection.execute(
        sa.text("SELECT key, payload FROM ln_settings WHERE key LIKE 'agent-model:%'")
    ):
        record = payload_of(value)
        records[key] = dict(record)
        record.pop("mode", None)
        previous = record.get("previous")
        if isinstance(previous, dict) and "preference" in previous:
            record["previous"] = cast(dict[str, Any], previous)["preference"]
        if record.get("chosen_by") == "agent":
            if owner_named(connection, record):
                record["chosen_by"] = "owner"
            else:
                record["chosen_by"], record["chosen_by_agent_id"] = None, None
        put(connection, key, record, now)
    allowed = connection.execute(
        sa.text("SELECT payload FROM ln_settings WHERE key = :key"), {"key": ALLOWED_KEY}
    ).scalar()
    connection.execute(sa.text("DELETE FROM ln_settings WHERE key = :key"), {"key": ALLOWED_KEY})
    marker = {
        "records": records,
        "allowed": payload_of(allowed) if allowed is not None else None,
    }
    connection.execute(
        sa.text("INSERT INTO ln_settings (key, payload, updated_at) VALUES (:key, :payload, :now)"),
        {"key": MARKER, "payload": json.dumps(marker), "now": now},
    )
    connection.execute(
        sa.text(
            "UPDATE ln_owner_actions SET status = 'superseded',"
            " status_reason = 'model_cards_removed', updated_at = :now"
            f" WHERE kind IN {KINDS} AND status = 'pending'"
        ),
        {"now": now},
    )
    connection.execute(
        sa.text(f"CREATE TABLE {RETIRED} AS SELECT * FROM ln_owner_actions WHERE kind IN {KINDS}")
    )
    connection.execute(sa.text(f"DELETE FROM ln_owner_actions WHERE kind IN {KINDS}"))


def downgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)
    marker = payload_of(
        connection.execute(
            sa.text("SELECT payload FROM ln_settings WHERE key = :key"), {"key": MARKER}
        ).scalar()
    )
    originals = cast(dict[str, Any], marker.get("records", {}))
    for key, value in connection.execute(
        sa.text("SELECT key, payload FROM ln_settings WHERE key LIKE 'agent-model:%'")
    ):
        record = payload_of(value)
        original = payload_of(originals.get(key))
        if original and original.get("revision") == record.get("revision"):
            put(connection, key, original, now)
            continue
        # Written after the upgrade: the old shape (no mode reads by its primary).
        previous = record.get("previous")
        if isinstance(previous, dict):
            primary = cast(dict[str, Any], previous).get("primary")
            record["previous"] = {
                "mode": "fixed" if primary else "automatic",
                "preference": previous,
            }
        if record.get("chosen_by") == "inherited":
            record["chosen_by"], record["chosen_by_agent_id"] = None, None
        put(connection, key, record, now)
    if marker.get("allowed") is not None:
        connection.execute(
            sa.text(
                "INSERT INTO ln_settings (key, payload, updated_at) VALUES (:key, :payload, :now)"
            ),
            {"key": ALLOWED_KEY, "payload": json.dumps(marker["allowed"]), "now": now},
        )
    connection.execute(sa.text("DELETE FROM ln_settings WHERE key = :key"), {"key": MARKER})
    connection.execute(sa.text(f"INSERT INTO ln_owner_actions SELECT * FROM {RETIRED}"))
    connection.execute(sa.text(f"DROP TABLE {RETIRED}"))
