"""The generic GenUI card kind ``receipt`` becomes ``summary`` (mandate 10.3, 6.10).

An agent's card no longer bears the name of the fixed Execution Receipt. Stored cards keep
rendering: every v2 card part of kind ``receipt`` in ``ln_messages.rich_content`` and in a
run's result card (``ln_runs.model_metadata.rich_content``) becomes ``summary``; nothing
else changes. Events already sent are history and are not rewritten. The downgrade
renames them back.
"""

import json
from typing import Any, cast

import sqlalchemy as sa
from alembic import op

revision = "0102_genui_summary_kind"
down_revision = "0131_agent_model_owner_only"
branch_labels = None
depends_on = None


def renamed(content: Any, old: str, new: str) -> bool:
    """Rename the kind of every v2 card part of ``content`` (rich content); True if any."""
    listed: Any = cast(dict[str, Any], content).get("parts") if isinstance(content, dict) else None
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
    return changed


def rename(old: str, new: str) -> None:
    bind = op.get_bind()
    like = {"kind": '%"' + old + '"%'}
    for identifier, raw in bind.execute(
        sa.text(
            "SELECT id, rich_content FROM ln_messages "
            "WHERE rich_content IS NOT NULL AND CAST(rich_content AS TEXT) LIKE :kind"
        ),
        like,
    ).all():
        content: Any = json.loads(raw) if isinstance(raw, str) else raw
        if renamed(content, old, new):
            bind.execute(
                sa.text(
                    "UPDATE ln_messages SET rich_content = CAST(:content AS JSON) WHERE id = :id"
                ),
                {"content": json.dumps(content, ensure_ascii=False), "id": identifier},
            )
    # A run's result card (model_metadata.rich_content), which a peer's outcome return reads.
    for identifier, raw in bind.execute(
        sa.text(
            "SELECT id, model_metadata FROM ln_runs WHERE CAST(model_metadata AS TEXT) LIKE :kind"
        ),
        like,
    ).all():
        metadata: Any = json.loads(raw) if isinstance(raw, str) else raw
        if isinstance(metadata, dict) and renamed(
            cast(dict[str, Any], metadata).get("rich_content"), old, new
        ):
            bind.execute(
                sa.text(
                    "UPDATE ln_runs SET model_metadata = CAST(:metadata AS JSON) WHERE id = :id"
                ),
                {"metadata": json.dumps(metadata, ensure_ascii=False), "id": identifier},
            )


def upgrade() -> None:
    rename("receipt", "summary")


def downgrade() -> None:
    rename("summary", "receipt")
