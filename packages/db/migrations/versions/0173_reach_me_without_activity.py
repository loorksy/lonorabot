"""The reach-me choice "activity only" is removed (mandate P5).

Its record was the activity log page, which is not one of the surfaces the app keeps
outside conversations. A stored reach-me preference that names it becomes the default
"message" (a message in the agent's conversation), so it validates against the
contract again. The owner did not make that change, so it is recorded in the owner's
preference history as a change by the system (shown as Lonora): "activity only" to
"message". Earlier revisions keep what the owner chose; undoing one that would bring
"activity only" back is refused (``reach_me_choice_removed``). The downgrade leaves
the moved preferences and their recorded change as they are.
"""

import json
import uuid
from datetime import UTC, datetime
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0173_reach_me_without_activity"
down_revision = "0088_end_notice_cards"
branch_labels = None
depends_on = None

KEY = "incoming-call-policy:"


def payload_of(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return dict(value or {})


def snapshot(connection: Any, owner_id: str, reach_me: dict[str, Any]) -> str:
    """The preferences text a revision stores (preferences_snapshot's canonical JSON)."""
    profile = connection.execute(
        sa.text("SELECT reply_language, name, address FROM ln_owner_profile WHERE owner_id = :o"),
        {"o": owner_id},
    ).first()
    return json.dumps(
        {
            "reply_language": profile[0] if profile else None,
            "reach_me": reach_me,
            "name": profile[1] if profile else None,
            "address": profile[2] if profile else None,
        },
        sort_keys=True,
        ensure_ascii=False,
    )


def upgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)
    for key, stored in connection.execute(
        sa.text("SELECT key, payload FROM ln_settings WHERE key LIKE 'incoming-call-policy:%'")
    ).all():
        payload = payload_of(stored)
        if payload.get("channel") != "activity":
            continue
        moved = {**payload, "channel": "message"}
        connection.execute(
            sa.text("UPDATE ln_settings SET payload = CAST(:payload AS JSON) WHERE key = :key"),
            {"key": key, "payload": json.dumps(moved)},
        )
        owner_id = str(key)[len(KEY) :]
        owner = connection.execute(
            sa.text("SELECT 1 FROM ln_owners WHERE id = :o"), {"o": owner_id}
        )
        if owner.first() is None:
            continue
        version = connection.execute(
            sa.text(
                "SELECT COALESCE(MAX(version), 0) + 1 FROM ln_memory_revisions "
                "WHERE owner_id = :o AND document = 'owner_preferences' AND agent_id IS NULL"
            ),
            {"o": owner_id},
        ).scalar_one()
        connection.execute(
            sa.text(
                "INSERT INTO ln_memory_revisions (id, owner_id, document, agent_id, version, "
                "previous_content, content, author, change, created_at) VALUES (:id, :o, "
                "'owner_preferences', NULL, :version, :previous, :content, 'system', "
                "'choice_removed', :now)"
            ),
            {
                "id": str(uuid.uuid4()),
                "o": owner_id,
                "version": version,
                "previous": snapshot(connection, owner_id, payload),
                "content": snapshot(connection, owner_id, moved),
                "now": now,
            },
        )


def downgrade() -> None:
    pass
