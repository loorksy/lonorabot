"""The grant card kind is gone (mandate 10.3.2, 14.3.9).

0128 already deleted every ``grant_authority`` card. This repeats that delete, with the
same ``owner_action.updated`` event, so a card written by the previous release after
0128, or left in a database that skipped it, is gone before this release serves. The
delete is idempotent. The downgrade restores nothing: a deleted card is not a grant.
"""

import json
from datetime import UTC, datetime

import sqlalchemy as sa
from alembic import op

revision = "0129_grant_cards_gone"
down_revision = "0128_authority_migration"
branch_labels = None
depends_on = None


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(UTC)
    owners = bind.execute(sa.text("SELECT id FROM ln_owners ORDER BY id")).all()
    for (owner_id,) in owners:
        bind.execute(
            sa.text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "owner-actions:" + owner_id},
        )
    cards = bind.execute(
        sa.text(
            "DELETE FROM ln_owner_actions WHERE kind = 'grant_authority' RETURNING id,"
            " owner_id, agent_id, thread_id, run_id, kind, status, status_reason"
        )
    ).all()
    for card in cards:
        bind.execute(
            sa.text(
                "INSERT INTO ln_events (owner_id, thread_id, agent_id, run_id, kind, payload,"
                " created_at) VALUES (:owner, :thread, :agent, :run, 'owner_action.updated',"
                " CAST(:payload AS JSON), :now)"
            ),
            {
                "owner": card.owner_id,
                "thread": card.thread_id,
                "agent": card.agent_id,
                "run": card.run_id,
                "payload": json.dumps(
                    {
                        "id": card.id,
                        "kind": card.kind,
                        "status": card.status,
                        "status_reason": card.status_reason,
                        "thread_id": card.thread_id,
                        "transition_id": card.id + ":deleted",
                    },
                    ensure_ascii=False,
                ),
                "now": now,
            },
        )


def downgrade() -> None:
    """Deleted cards stay deleted. Nothing here grants authority."""
    return None
