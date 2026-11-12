"""The reach-me choice "activity only" is removed (mandate P5).

Its record was the activity log page, which is not one of the surfaces the app keeps
outside conversations. A stored reach-me preference that names it becomes the default
"message" (a message in the agent's conversation), so it validates against the
contract again. The owner-preference revisions that name it, before or after a
change, are rewritten the same way, so undoing such a change still validates and
its history names a choice that exists. The downgrade leaves the rewritten
preferences as they are.
"""

import json
from typing import Any

import sqlalchemy as sa
from alembic import op

revision = "0173_reach_me_without_activity"
down_revision = "0138_skill_package_files"
branch_labels = None
depends_on = None


def payload_of(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return dict(value or {})


def without_activity(content: str) -> str | None:
    """A revision's preferences text with "activity" read as "message", or None when
    the text names no "activity" choice (or is not the canonical JSON)."""
    try:
        snapshot = json.loads(content)
    except ValueError:
        return None
    if not isinstance(snapshot, dict):
        return None
    reach_me = snapshot.get("reach_me")
    if not isinstance(reach_me, dict) or reach_me.get("channel") != "activity":
        return None
    snapshot["reach_me"] = {**reach_me, "channel": "message"}
    # The canonical text preferences_snapshot writes.
    return json.dumps(snapshot, sort_keys=True, ensure_ascii=False)


def upgrade() -> None:
    connection = op.get_bind()
    for key, stored in connection.execute(
        sa.text("SELECT key, payload FROM ln_settings WHERE key LIKE 'incoming-call-policy:%'")
    ).all():
        payload = payload_of(stored)
        if payload.get("channel") != "activity":
            continue
        connection.execute(
            sa.text("UPDATE ln_settings SET payload = CAST(:payload AS JSON) WHERE key = :key"),
            {"key": key, "payload": json.dumps({**payload, "channel": "message"})},
        )
    for revision_id, previous, content in connection.execute(
        sa.text(
            "SELECT id, previous_content, content FROM ln_memory_revisions "
            "WHERE document = 'owner_preferences'"
        )
    ).all():
        new_previous, new_content = without_activity(previous), without_activity(content)
        if new_previous is None and new_content is None:
            continue
        connection.execute(
            sa.text(
                "UPDATE ln_memory_revisions SET previous_content = :previous, "
                "content = :content WHERE id = :id"
            ),
            {
                "id": revision_id,
                "previous": previous if new_previous is None else new_previous,
                "content": content if new_content is None else new_content,
            },
        )


def downgrade() -> None:
    pass
