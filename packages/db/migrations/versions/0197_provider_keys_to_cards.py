"""Settings-era model keys move to the Secret card's record; the ``provider`` scope goes.

The provider settings screens are removed (P5): a model provider's key is connected from
chat, saved as a workspace secret under the provider's usual name with a
``model_provider:<provider>`` record that the router reads (Q14 (b)). A key those screens
saved has scope ``provider`` and the provider's id as its name. Each moves as its
ciphertext, which does not depend on its scope or name:

- with no card record, it becomes that workspace secret, recorded for the router. If the
  owner's own workspace secret already holds the usual name, that secret is left alone
  and the key takes the next free name (``ZAI_API_KEY_2``);
- with a card record whose key was saved later, it is dropped: the router no longer used
  it;
- with a card record whose key is older, its value replaces that card secret's.

A ``provider`` key under a name that is no provider stops the upgrade with its name:
nothing ever wrote one. The scope then leaves the CHECK. The downgrade restores the
scope only: the earlier release reads every key from its card record.

This revision also joins the two heads of W-MODELS' chain (0195 and 0196).
"""

import json

import sqlalchemy as sa
from alembic import op

revision = "0197_provider_keys_to_cards"
down_revision = ("0195_drop_model_backups", "0196_model_provider_cards")
branch_labels = None
depends_on = None

# lonora_contracts.model_routing.PROVIDER_KEY_NAMES as this revision found it; the owner's
# own endpoint was never saved on the settings screens.
KEY_NAMES = {
    "anthropic": "ANTHROPIC_API_KEY",
    "openai": "OPENAI_API_KEY",
    "deepseek": "DEEPSEEK_API_KEY",
    "openrouter": "OPENROUTER_API_KEY",
    "zai": "ZAI_API_KEY",
}
RECORD = "model_provider:"
SCOPES = "scope IN ('broker','provider','integration','workspace')"
WITHOUT_PROVIDER = "scope IN ('broker','integration','workspace')"


def free_name(base: str, taken: set[str]) -> str:
    candidate, number = base, 1
    while candidate in taken:
        number += 1
        candidate = f"{base}_{number}"
    taken.add(candidate)
    return candidate


def upgrade() -> None:
    bind = op.get_bind()
    legacy = bind.execute(
        sa.text(
            "SELECT id, name, ciphertext, updated_at FROM ln_secrets"
            " WHERE scope = 'provider' ORDER BY name"
        )
    ).all()
    unknown = sorted({row.name for row in legacy} - set(KEY_NAMES))
    if unknown:
        raise RuntimeError("provider-scope keys under no provider's name: " + ", ".join(unknown))
    taken = set(
        bind.execute(sa.text("SELECT name FROM ln_secrets WHERE scope = 'workspace'")).scalars()
    )
    for row in legacy:
        stored = bind.execute(
            sa.text("SELECT payload::text FROM ln_settings WHERE key = :key"),
            {"key": RECORD + row.name},
        ).scalar()
        card_id = json.loads(stored).get("secret_id") if stored else None
        card = (
            bind.execute(
                sa.text("SELECT id, updated_at FROM ln_secrets WHERE id = :id"), {"id": card_id}
            ).first()
            if card_id
            else None
        )
        if card is not None:
            if row.updated_at > card.updated_at:
                bind.execute(
                    sa.text(
                        "UPDATE ln_secrets SET ciphertext = :ciphertext, updated_at = :at"
                        " WHERE id = :id"
                    ),
                    {"ciphertext": row.ciphertext, "at": row.updated_at, "id": card.id},
                )
            bind.execute(sa.text("DELETE FROM ln_secrets WHERE id = :id"), {"id": row.id})
            continue
        bind.execute(
            sa.text("UPDATE ln_secrets SET scope = 'workspace', name = :name WHERE id = :id"),
            {"name": free_name(KEY_NAMES[row.name], taken), "id": row.id},
        )
        bind.execute(
            sa.text(
                "INSERT INTO ln_settings (key, payload, updated_at) VALUES (:key, :payload, now())"
                " ON CONFLICT (key) DO UPDATE SET payload = excluded.payload,"
                " updated_at = excluded.updated_at"
            ),
            {"key": RECORD + row.name, "payload": json.dumps({"secret_id": row.id, "url": None})},
        )
    op.drop_constraint("ln_secret_scope", "ln_secrets", type_="check")
    op.create_check_constraint("ln_secret_scope", "ln_secrets", WITHOUT_PROVIDER)


def downgrade() -> None:
    op.drop_constraint("ln_secret_scope", "ln_secrets", type_="check")
    op.create_check_constraint("ln_secret_scope", "ln_secrets", SCOPES)
