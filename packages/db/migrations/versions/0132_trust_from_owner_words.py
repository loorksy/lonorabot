"""An agent trusts a source on the owner's own words; the trust card goes (VISION 10.3.2,
lead decision Q21 (b)).

- ``ln_trusted_sources.added_via`` gains ``owner_message``: a source an agent added
  because the owner's typed message the run answered named it. Rows added from the trust
  card keep ``owner_card``.
- Trust cards (``trust_source``): a pending one is settled as ``superseded``
  (``trust_cards_removed``), then every one moves to ``ln_owner_actions_trust_retired``,
  which nothing reads, so no card list meets a kind the clients no longer render.
  Nothing is erased.

The downgrade puts the retired cards back (settled ones stay settled: a downgrade never
reopens a card) and reads an ``owner_message`` entry as ``owner_card``, the old schema's
nearest value; the ids it rewrote are kept in a marker row, so the upgrade that follows
restores ``owner_message`` exactly.
"""

import json
from datetime import UTC, datetime
from typing import Any, cast

import sqlalchemy as sa
from alembic import op

revision = "0132_trust_from_owner_words"
down_revision = "0131_agent_model_owner_only"
branch_labels = None
depends_on = None

MARKER = "migration:0132_trust_from_owner_words"
RETIRED = "ln_owner_actions_trust_retired"
CHECK = "ln_trusted_source_added_via"
NEW = "added_via IN ('default','operator','owner_ui','owner_card','owner_message')"
OLD = "added_via IN ('default','operator','owner_ui','owner_card')"


def payload_of(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def upgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)
    op.drop_constraint(CHECK, "ln_trusted_sources", type_="check")
    op.create_check_constraint(CHECK, "ln_trusted_sources", NEW)
    marker = payload_of(
        connection.execute(
            sa.text("SELECT payload FROM ln_settings WHERE key = :key"), {"key": MARKER}
        ).scalar()
    )
    restored = [str(item) for item in marker.get("owner_message", [])]
    if restored:
        connection.execute(
            sa.text(
                "UPDATE ln_trusted_sources SET added_via = 'owner_message'"
                " WHERE id IN :ids AND added_via = 'owner_card'"
            ).bindparams(sa.bindparam("ids", expanding=True)),
            {"ids": restored},
        )
    connection.execute(sa.text("DELETE FROM ln_settings WHERE key = :key"), {"key": MARKER})
    connection.execute(
        sa.text(
            "UPDATE ln_owner_actions SET status = 'superseded',"
            " status_reason = 'trust_cards_removed', updated_at = :now"
            " WHERE kind = 'trust_source' AND status = 'pending'"
        ),
        {"now": now},
    )
    connection.execute(
        sa.text(
            f"CREATE TABLE {RETIRED} AS SELECT * FROM ln_owner_actions WHERE kind = 'trust_source'"
        )
    )
    connection.execute(sa.text("DELETE FROM ln_owner_actions WHERE kind = 'trust_source'"))


def downgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)
    rewritten = [
        str(item)
        for item in connection.execute(
            sa.text("SELECT id FROM ln_trusted_sources WHERE added_via = 'owner_message'")
        ).scalars()
    ]
    connection.execute(
        sa.text(
            "UPDATE ln_trusted_sources SET added_via = 'owner_card'"
            " WHERE added_via = 'owner_message'"
        )
    )
    if rewritten:
        connection.execute(
            sa.text(
                "INSERT INTO ln_settings (key, payload, updated_at) VALUES (:key, :payload, :now)"
            ),
            {"key": MARKER, "payload": json.dumps({"owner_message": rewritten}), "now": now},
        )
    op.drop_constraint(CHECK, "ln_trusted_sources", type_="check")
    op.create_check_constraint(CHECK, "ln_trusted_sources", OLD)
    connection.execute(sa.text(f"INSERT INTO ln_owner_actions SELECT * FROM {RETIRED}"))
    connection.execute(sa.text(f"DROP TABLE {RETIRED}"))
