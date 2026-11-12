"""The owner's MetaApi token is one broker secret named ``metaapi_token``.

Until now each MetaApi connection stored its own copy of the token under the MetaApi
account id. When an owner's MetaApi connections refer to exactly one broker secret, that
secret is renamed ``metaapi_token``. The row, its id and its ciphertext are unchanged, so
every connection keeps working. When they refer to several, values cannot be compared
without decrypting them, so nothing is renamed. The downgrade restores the account-id
name when exactly one connection refers to the token and that name is free.
"""

import sqlalchemy as sa
from alembic import op

revision = "0145_metaapi_token"
down_revision = "0176_weekly_reports"
branch_labels = None
depends_on = None

TOKEN = "metaapi_token"


def upgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT DISTINCT b.owner_id, s.id FROM ln_broker_sessions b "
            "JOIN ln_secrets s ON s.id = b.payload->>'secret_id' "
            "WHERE b.payload->>'provider' = 'metaapi' AND s.scope = 'broker' "
            "AND s.owner_id = b.owner_id"
        )
    ).all()
    by_owner: dict[str, set[str]] = {}
    for owner_id, secret_id in rows:
        by_owner.setdefault(owner_id, set()).add(secret_id)
    for owner_id, secrets in by_owner.items():
        if len(secrets) != 1:
            continue
        taken = connection.scalar(
            sa.text("SELECT 1 FROM ln_secrets WHERE scope = 'broker' AND name = :name"),
            {"name": TOKEN},
        )
        if taken:
            continue
        connection.execute(
            sa.text("UPDATE ln_secrets SET name = :name WHERE id = :id AND owner_id = :owner"),
            {"name": TOKEN, "id": next(iter(secrets)), "owner": owner_id},
        )


def downgrade() -> None:
    connection = op.get_bind()
    rows = connection.execute(
        sa.text(
            "SELECT s.id, b.payload->>'account_id' FROM ln_secrets s "
            "JOIN ln_broker_sessions b ON b.payload->>'secret_id' = s.id "
            "AND b.owner_id = s.owner_id WHERE s.scope = 'broker' AND s.name = :name"
        ),
        {"name": TOKEN},
    ).all()
    if len(rows) != 1:
        return
    secret_id, account_id = rows[0]
    taken = connection.scalar(
        sa.text("SELECT 1 FROM ln_secrets WHERE scope = 'broker' AND name = :name"),
        {"name": account_id},
    )
    if not taken:
        connection.execute(
            sa.text("UPDATE ln_secrets SET name = :name WHERE id = :id"),
            {"name": account_id, "id": secret_id},
        )
