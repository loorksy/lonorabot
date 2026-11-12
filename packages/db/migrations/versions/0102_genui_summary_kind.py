"""The generic GenUI card kind ``receipt`` becomes ``summary`` (mandate 10.3, 6.10).

An agent's card no longer bears the name of the fixed Execution Receipt. Stored assistant
messages keep rendering: every v2 card part of kind ``receipt`` in ``ln_messages.
rich_content`` becomes ``summary``; nothing else in the document changes. The downgrade
renames them back.
"""

import json
from typing import Any, cast

import sqlalchemy as sa
from alembic import op

revision = "0102_genui_summary_kind"
down_revision = "0176_weekly_reports"
branch_labels = None
depends_on = None


def rename(old: str, new: str) -> None:
    bind = op.get_bind()
    rows = bind.execute(
        sa.text(
            "SELECT id, rich_content FROM ln_messages "
            "WHERE rich_content IS NOT NULL AND CAST(rich_content AS TEXT) LIKE :kind"
        ),
        {"kind": '%"' + old + '"%'},
    ).all()
    for identifier, raw in rows:
        content: Any = json.loads(raw) if isinstance(raw, str) else raw
        listed: Any = (
            cast(dict[str, Any], content).get("parts") if isinstance(content, dict) else None
        )
        parts = cast(list[Any], listed) if isinstance(listed, list) else []
        changed = False
        for part in parts:
            if not isinstance(part, dict):
                continue
            entry = cast(dict[str, Any], part)
            document = entry.get("document")
            if entry.get("type") != "ui" or not isinstance(document, dict):
                continue
            card = cast(dict[str, Any], document)
            if card.get("v") == 2 and card.get("kind") == old:
                card["kind"] = new
                changed = True
        if changed:
            bind.execute(
                sa.text(
                    "UPDATE ln_messages SET rich_content = CAST(:content AS JSON) WHERE id = :id"
                ),
                {"content": json.dumps(content), "id": identifier},
            )


def upgrade() -> None:
    rename("receipt", "summary")


def downgrade() -> None:
    rename("summary", "receipt")
