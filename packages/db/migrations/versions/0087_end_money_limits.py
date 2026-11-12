"""Execution caps and money limits are removed (mandate 14.2.2, 14.3.9).

* Each account's stored execution policy (``ln_settings`` keys ``execution_policy:*``)
  keeps only its quote and account freshness bounds; the caps and the money limits
  (``max_spread``, ``max_entry_drift_stop_fraction``, ``max_positions``,
  ``max_pending_orders``, ``max_symbol_direction_volume`` and ``risk``) are stripped.
* Owner action cards of the removed ``set_account_limits`` kind are deleted: the contract
  no longer accepts that kind.
* Grant cards no longer carry a daily loss limit: ``daily_loss`` is stripped from each
  draft and from its Custom terms, and the payload hash is recomputed. Two pending cards
  of one agent that differed only in their daily loss now ask for the same effect: the
  older one is superseded, as when the owner's choice matches another card.
* Passkey challenges of the removed execution-policy route (``execution_policy``) and of
  the removed limits card (``owner_action``, which only that card issued) are deleted.

The downgrade changes no data: the older contracts read the removed fields as unset.
The deleted cards and challenges and the stripped values are not restored.
"""

import json
from datetime import UTC, datetime
from hashlib import sha256
from typing import Any, cast

import sqlalchemy as sa
from alembic import op

revision = "0087_end_money_limits"
down_revision = "0138_skill_package_files"
branch_labels = None
depends_on = None

REMOVED_POLICY = (
    "max_spread",
    "max_entry_drift_stop_fraction",
    "max_positions",
    "max_pending_orders",
    "max_symbol_direction_volume",
    "risk",
)


def payload_of(value: Any) -> dict[str, Any]:
    if isinstance(value, str):
        value = json.loads(value)
    return cast(dict[str, Any], value) if isinstance(value, dict) else {}


def dump(value: Any) -> str:
    return json.dumps(value, separators=(",", ":"), ensure_ascii=False)


def payload_hash(kind: str, payload: dict[str, Any]) -> str:
    """Frozen copy of lonora_db.owner_actions.payload_hash."""
    return sha256(
        json.dumps(
            {"kind": kind, "payload": payload},
            sort_keys=True,
            separators=(",", ":"),
            ensure_ascii=False,
        ).encode()
    ).hexdigest()


def without_daily_loss(payload: dict[str, Any]) -> dict[str, Any]:
    draft = {key: value for key, value in payload.items() if key != "daily_loss"}
    custom = draft.get("custom")
    if isinstance(custom, dict):
        terms = cast(dict[str, Any], custom)
        draft["custom"] = {key: value for key, value in terms.items() if key != "daily_loss"}
    return draft


def upgrade() -> None:
    connection = op.get_bind()
    now = datetime.now(UTC)
    for key, raw in connection.execute(
        sa.text("SELECT key, payload FROM ln_settings WHERE key LIKE 'execution_policy:%'")
    ).all():
        policy = payload_of(raw)
        kept = {name: value for name, value in policy.items() if name not in REMOVED_POLICY}
        if kept != policy:
            connection.execute(
                sa.text("UPDATE ln_settings SET payload = CAST(:payload AS JSON) WHERE key = :key"),
                {"key": key, "payload": dump(kept)},
            )

    connection.execute(sa.text("DELETE FROM ln_owner_actions WHERE kind = 'set_account_limits'"))

    grants = connection.execute(
        sa.text(
            "SELECT id, agent_id, payload, payload_hash, status FROM ln_owner_actions"
            " WHERE kind = 'grant_authority' ORDER BY created_at, id"
        )
    ).all()
    changed: dict[str, tuple[dict[str, Any], str]] = {}
    # The newest pending card of each agent and effect stays; an older one gives way first,
    # so the one-pending-card-per-effect index never sees two.
    pending: dict[tuple[str, str], str] = {}
    superseded: list[str] = []
    for row in grants:
        payload = payload_of(row.payload)
        draft = without_daily_loss(payload)
        digest = row.payload_hash
        if draft != payload:
            digest = payload_hash("grant_authority", draft)
            changed[row.id] = (draft, digest)
        if row.status == "pending":
            older = pending.get((row.agent_id, digest))
            if older is not None:
                superseded.append(older)
            pending[(row.agent_id, digest)] = row.id
    for identifier in superseded:
        connection.execute(
            sa.text(
                "UPDATE ln_owner_actions SET status = 'superseded',"
                " status_reason = 'same_choice_on_another_card', updated_at = :now"
                " WHERE id = :id"
            ),
            {"id": identifier, "now": now},
        )
    for identifier, (draft, digest) in changed.items():
        connection.execute(
            sa.text(
                "UPDATE ln_owner_actions SET payload = CAST(:payload AS JSON),"
                " payload_hash = :hash WHERE id = :id"
            ),
            {"id": identifier, "payload": dump(draft), "hash": digest},
        )

    connection.execute(
        sa.text(
            "DELETE FROM ln_device_challenges WHERE kind IN ('execution_policy', 'owner_action')"
        )
    )


def downgrade() -> None:
    pass
