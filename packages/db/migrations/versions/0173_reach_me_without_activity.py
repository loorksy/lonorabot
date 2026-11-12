"""The reach-me choice "activity only" is removed (mandate P5).

Its record was the activity log page, which is not one of the surfaces the app keeps
outside conversations. A stored reach-me preference that names it becomes the default
"message" (a message in the agent's conversation), so it validates against the
contract again. The downgrade leaves the rewritten preferences as they are.
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


def downgrade() -> None:
    pass
