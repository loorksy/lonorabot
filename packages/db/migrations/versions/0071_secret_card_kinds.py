"""The credential card becomes the Secret card (VISION.md 10.3.2).

Every ``connect_credential`` row becomes a ``secret`` row that connects the same target,
so a settled card still reads "Connected" in its conversation. Its stored payload
(``target``, ``service``) becomes the Secret card's (``connect``, ``service``, ``details``,
``fields``, ``destination``). A trading account is now connected with broker_connect's
card, so a converted ``broker`` card is only ever a settled record. A pending one cannot
be saved as it was (its form asked for details the agent now gives from chat), so it is
settled ``expired`` with the reason ``card_kind_removed``; nothing wakes its agent, and a
new card is raised when the connection is asked for again. ``payload_hash`` is kept: it
only deduplicates pending cards, and none is pending after this. A row whose target is
not one of the five stops the upgrade with its id: nothing ever wrote one.

The downgrade turns connecting Secret cards back into ``connect_credential`` rows (the
expiry stays) and an agent's own card back into the shape the earlier code reads (its
label, fields and destination); a broker card raised by the broker tools is the same in
both. It refuses while a feed, a calendar or an MCP server saved from a Secret card
exists: its address is in the encrypted store, which the earlier code cannot read.
Remove those connections first.
"""

import json
from datetime import UTC, datetime
from typing import cast

import sqlalchemy as sa
from alembic import op

revision = "0071_secret_card_kinds"
down_revision = "0139_workspace_running"
branch_labels = None
depends_on = None

# A connecting card's fields (key, role, required, masked) and its destination, as
# ``lonora_db.secret_cards`` has them; a broker card is only a settled record, so its
# field needs no role.
CONNECTING: dict[str, tuple[tuple[tuple[str, str | None, bool, bool], ...], str]] = {
    "mcp_server": (
        (("URL", "server_url", True, False), ("TOKEN", "token", False, True)),
        "workspace",
    ),
    "brave_search": ((("API_KEY", "api_key", True, True),), "workspace"),
    "news_feed": ((("URL", "feed_url", True, False),), "workspace"),
    "economic_calendar": ((("URL", "feed_url", True, False),), "workspace"),
    "broker": ((("METAAPI_TOKEN", None, True, True),), "broker"),
}


def payload_of(raw: object) -> dict[str, object]:
    return json.loads(raw) if isinstance(raw, str) else dict(raw or {})  # type: ignore[arg-type]


def upgrade() -> None:
    bind = op.get_bind()
    now = datetime.now(UTC)
    bind.execute(
        sa.text(
            "UPDATE ln_owner_actions SET status = 'expired', status_reason = 'card_kind_removed', "
            "updated_at = :now WHERE kind = 'connect_credential' AND status = 'pending'"
        ),
        {"now": now},
    )
    rows = bind.execute(
        sa.text("SELECT id, payload FROM ln_owner_actions WHERE kind = 'connect_credential'")
    ).all()
    for card_id, raw in rows:
        old = payload_of(raw)
        target = str(old.get("target"))
        if target not in CONNECTING:
            # Nothing ever wrote another target; such a row is not guessed into one.
            raise RuntimeError("connect_credential card " + str(card_id) + " has no known target")
        fields, destination = CONNECTING[target]
        payload: dict[str, object] = {
            "label": None,
            "connect": target,
            "service": old.get("service"),
            "details": {},
            "fields": [
                {"key": key, "label": None, "secret": masked, "role": role, "required": required}
                for key, role, required, masked in fields
            ],
            "destination": destination,
        }
        bind.execute(
            sa.text(
                "UPDATE ln_owner_actions SET kind = 'secret', payload = :payload WHERE id = :id"
            ),
            {"payload": json.dumps(payload), "id": card_id},
        )


def downgrade() -> None:
    bind = op.get_bind()
    stored = bind.execute(
        sa.text(
            "SELECT (SELECT count(*) FROM ln_integrations WHERE payload->>'domain' IS NOT NULL)"
            " + (SELECT count(*) FROM ln_mcp_connections"
            " WHERE payload->>'url_secret_id' IS NOT NULL)"
        )
    ).scalar_one()
    if stored:
        raise RuntimeError(
            f"{stored} connection(s) saved from a Secret card keep their address in the "
            "encrypted store, which the earlier release cannot read: remove them first"
        )
    rows = bind.execute(
        sa.text("SELECT id, payload FROM ln_owner_actions WHERE kind = 'secret'")
    ).all()
    for card_id, raw in rows:
        payload = payload_of(raw)
        if payload.get("account") is not None:
            continue  # A broker card from the broker tools: the earlier code shows it.
        if not payload.get("connect"):
            # An agent's own card, as the earlier code reads it.
            fields = cast(list[dict[str, object]], payload["fields"])
            own = {
                "label": payload["label"],
                "fields": [
                    {key: field[key] for key in ("key", "label", "secret")} for field in fields
                ],
                "destination": payload["destination"],
            }
            bind.execute(
                sa.text("UPDATE ln_owner_actions SET payload = :payload WHERE id = :id"),
                {"payload": json.dumps(own), "id": card_id},
            )
            continue
        old = {"target": payload["connect"], "service": payload.get("service")}
        bind.execute(
            sa.text(
                "UPDATE ln_owner_actions SET kind = 'connect_credential', payload = :payload "
                "WHERE id = :id"
            ),
            {"payload": json.dumps(old), "id": card_id},
        )
