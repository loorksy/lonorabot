"""Migration 0196 keeps a downgraded release from reading a model provider's card.

A Secret card that connects a model provider is only written by this release. 0071's
downgrade would turn it into a ``connect_credential`` row whose target the earlier
contracts refuse. On a disposable PostgreSQL at head: store such a card. The downgrade
refuses while it exists and changes nothing; once it is removed, the downgrade runs and
the upgrade runs again cleanly.
"""

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from check_streaming import test_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
BEFORE = "0196_model_provider_cards-1"
CARD = {
    "connect": "model_provider",
    "service": None,
    "details": {"provider": "openai"},
    "fields": [{"key": "API_KEY", "label": None, "secret": True, "role": "api_key"}],
    "destination": "workspace",
    "label": None,
}


def alembic(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*ALEMBIC, *arguments], capture_output=True, text=True, check=False)


def current() -> str:
    return alembic("current").stdout.strip()


async def main() -> None:
    url = test_settings().database_url
    assert alembic("upgrade", "head").returncode == 0
    head = current()
    engine = create_async_engine(url)
    card_id = str(uuid4())
    now = datetime.now(UTC)
    try:
        async with engine.begin() as connection:
            owner_id = await connection.scalar(text("SELECT id FROM ln_owners LIMIT 1")) or str(
                uuid4()
            )
            await connection.execute(
                text(
                    "INSERT INTO ln_owners (id, singleton, email, password_hash, created_at)"
                    " VALUES (:id, 1, 'model-card-migration@example.com', 'x', :now)"
                    " ON CONFLICT DO NOTHING"
                ),
                {"id": owner_id, "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO ln_owner_actions (id, owner_id, agent_id, source, kind,"
                    " subject, payload, payload_hash, status, result, expires_at,"
                    " created_at, updated_at) VALUES (:id, :owner, :agent, 'agent', 'secret',"
                    " 'model_provider:openai', :payload, :hash, 'confirmed', '{}', :expires,"
                    " :now, :now)"
                ),
                {
                    "id": card_id,
                    "owner": owner_id,
                    "agent": str(uuid4()),
                    "payload": json.dumps(CARD),
                    "hash": "0" * 64,
                    "expires": now + timedelta(days=1),
                    "now": now,
                },
            )

        refused = alembic("downgrade", BEFORE)
        assert refused.returncode != 0 and "model provider" in refused.stderr, refused.stderr
        assert current() == head
        async with engine.connect() as connection:
            kept = await connection.scalar(
                text("SELECT payload::text FROM ln_owner_actions WHERE id = :id"), {"id": card_id}
            )
        assert json.loads(kept or "null") == CARD
        print("PASS the downgrade refuses while a model provider's card exists, unchanged")

        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM ln_owner_actions WHERE id = :id"), {"id": card_id}
            )
        downgraded = alembic("downgrade", BEFORE)
        assert downgraded.returncode == 0, downgraded.stderr
        assert alembic("upgrade", "head").returncode == 0
        assert current() == head
        print("PASS once it is removed, the downgrade and the upgrade run")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
