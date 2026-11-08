"""An explicit trading level for every agent that has none stored (data only).

Until now an agent without a stored permission row read as "No trading". New defaults
apply only to new agents: Lonora (the Personal Agent) and root trading agents start at
"Ask me", every other agent at "No trading". So that no existing agent changes behaviour
silently, each one without a row gets its level written explicitly: "No trading", except
the Personal Agent, which gets "Ask me" (every trade still waits for the owner's tap).

The keys this step inserted are recorded, and the downgrade deletes only those rows that
nobody changed since (revision 0). Running the upgrade again inserts nothing.
"""

import hashlib
import json
from datetime import UTC, datetime
from typing import Any, cast

import sqlalchemy as sa
from alembic import op

revision = "0040_explicit_agent_permission_rows"
down_revision = "0039_owner_profile_memory_revisions"
branch_labels = None
depends_on = None

MARKER = "migration:0040_explicit_agent_permission_rows"


def permission_key(owner_id: str, agent_id: str) -> str:
    """Frozen copy of lonora_db.agent_permissions.permission_key."""
    return "agent-permission:" + hashlib.sha256((owner_id + ":" + agent_id).encode()).hexdigest()


def record(owner_id: str, agent_id: str, role: str | None) -> dict[str, Any]:
    """Frozen PermissionRecord shape at revision 0."""
    return {
        "owner_id": owner_id,
        "agent_id": agent_id,
        "revision": 0,
        "fallback_level": "supervised" if role == "personal" else "analysis",
        "customization": None,
    }


def payload_of(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def upgrade() -> None:
    connection = op.get_bind()
    settings = sa.table(
        "ln_settings",
        sa.column("key", sa.String),
        sa.column("payload", sa.JSON),
        sa.column("updated_at", sa.DateTime(timezone=True)),
    )
    existing = set(
        connection.execute(
            sa.text("SELECT key FROM ln_settings WHERE key LIKE 'agent-permission:%'")
        ).scalars()
    )
    marker = connection.execute(
        sa.text("SELECT payload FROM ln_settings WHERE key = :key"), {"key": MARKER}
    ).scalar()
    inserted: list[str] = list(payload_of(marker).get("keys", [])) if marker is not None else []
    now = datetime.now(UTC)
    rows: list[dict[str, Any]] = []
    for agent_id, owner_id, role in connection.execute(
        sa.text("SELECT id, owner_id, role FROM ln_agents ORDER BY owner_id, created_at, id")
    ):
        key = permission_key(str(owner_id), str(agent_id))
        if key in existing:
            continue
        existing.add(key)
        rows.append(
            {
                "key": key,
                "payload": record(str(owner_id), str(agent_id), role),
                "updated_at": now,
            }
        )
        inserted.append(key)
    if rows:
        op.bulk_insert(settings, rows)
    payload = {"keys": sorted(set(inserted))}
    if marker is None:
        op.bulk_insert(settings, [{"key": MARKER, "payload": payload, "updated_at": now}])
    elif rows:
        connection.execute(
            settings.update()
            .where(settings.c.key == MARKER)
            .values(payload=payload, updated_at=now)
        )


def downgrade() -> None:
    connection = op.get_bind()
    marker = connection.execute(
        sa.text("SELECT payload FROM ln_settings WHERE key = :key"), {"key": MARKER}
    ).scalar()
    keys = set(payload_of(marker).get("keys", [])) if marker is not None else set[str]()
    untouched = [
        key
        for key, value in connection.execute(
            sa.text("SELECT key, payload FROM ln_settings WHERE key LIKE 'agent-permission:%'")
        )
        if key in keys and payload_of(value).get("revision") == 0
    ]
    for key in untouched:
        connection.execute(sa.text("DELETE FROM ln_settings WHERE key = :key"), {"key": key})
    connection.execute(sa.text("DELETE FROM ln_settings WHERE key = :key"), {"key": MARKER})
