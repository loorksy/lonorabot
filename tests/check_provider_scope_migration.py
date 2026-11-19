"""Migration 0197 moves every settings-era model key to the Secret card's record.

A key saved on the removed provider settings screens has scope ``provider`` and the
provider's id as its name. On a disposable PostgreSQL before 0197, store four such keys
beside the card records they meet, plus one under a name that is no provider. The
upgrade refuses that one and changes nothing. Without it, the upgrade:

- moves a key alone to the workspace under the provider's usual name, recorded for the
  router (OpenAI);
- drops a key older than its card's key (Anthropic);
- writes a key newer than its card's key into that card's secret (DeepSeek);
- leaves the owner's own workspace secret under the usual name alone and takes the next
  free name (Z.ai).

Each value moves as its ciphertext, unchanged. No ``provider`` scope remains, and a new
one is refused. The downgrade keeps every key where the earlier release reads it.
"""

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from check_streaming import test_settings
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
# The parent on the provider scope's side: downgrading to it removes 0197.
BEFORE = "0196_model_provider_cards"
RECORD = "model_provider:"


def alembic(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*ALEMBIC, *arguments], capture_output=True, text=True, check=False)


async def secret(
    connection: AsyncConnection, owner: str, scope: str, name: str, when: datetime
) -> tuple[str, str]:
    row_id, ciphertext = str(uuid4()), "ciphertext-" + uuid4().hex
    await connection.execute(
        text(
            "INSERT INTO ln_secrets (id, owner_id, scope, name, ciphertext, updated_at)"
            " VALUES (:id, :owner, :scope, :name, :ciphertext, :when)"
        ),
        {
            "id": row_id,
            "owner": owner,
            "scope": scope,
            "name": name,
            "ciphertext": ciphertext,
            "when": when,
        },
    )
    return row_id, ciphertext


async def record(connection: AsyncConnection, provider: str, secret_id: str) -> None:
    await connection.execute(
        text("INSERT INTO ln_settings (key, payload, updated_at) VALUES (:key, :payload, now())"),
        {"key": RECORD + provider, "payload": json.dumps({"secret_id": secret_id, "url": None})},
    )


async def secrets(connection: AsyncConnection) -> dict[tuple[str, str], tuple[str, str]]:
    rows = await connection.execute(text("SELECT scope, name, id, ciphertext FROM ln_secrets"))
    return {(row.scope, row.name): (row.id, row.ciphertext) for row in rows}


async def records(connection: AsyncConnection) -> dict[str, Any]:
    rows = await connection.execute(
        text("SELECT key, payload::text AS payload FROM ln_settings WHERE key LIKE :prefix"),
        {"prefix": RECORD + "%"},
    )
    return {row.key.removeprefix(RECORD): json.loads(row.payload) for row in rows}


async def main() -> None:
    url = test_settings().database_url
    assert alembic("upgrade", "heads").returncode == 0
    downgraded = alembic("downgrade", BEFORE)
    assert downgraded.returncode == 0, downgraded.stderr
    engine = create_async_engine(url)
    earlier = datetime.now(UTC) - timedelta(days=2)
    later = earlier + timedelta(days=1)
    try:
        async with engine.begin() as connection:
            owner = await connection.scalar(text("SELECT id FROM ln_owners LIMIT 1")) or str(
                uuid4()
            )
            await connection.execute(
                text(
                    "INSERT INTO ln_owners (id, singleton, email, password_hash, created_at)"
                    " VALUES (:id, 1, 'provider-scope@example.com', 'x', now())"
                    " ON CONFLICT DO NOTHING"
                ),
                {"id": owner},
            )
            openai = await secret(connection, owner, "provider", "openai", earlier)
            old_anthropic = await secret(connection, owner, "provider", "anthropic", earlier)
            card_anthropic = await secret(
                connection, owner, "workspace", "ANTHROPIC_API_KEY", later
            )
            await record(connection, "anthropic", card_anthropic[0])
            new_deepseek = await secret(connection, owner, "provider", "deepseek", later)
            card_deepseek = await secret(
                connection, owner, "workspace", "DEEPSEEK_API_KEY", earlier
            )
            await record(connection, "deepseek", card_deepseek[0])
            zai = await secret(connection, owner, "provider", "zai", earlier)
            own_zai = await secret(connection, owner, "workspace", "ZAI_API_KEY", earlier)
            mystery = await secret(connection, owner, "provider", "mystery", earlier)
        async with engine.connect() as connection:
            before = await secrets(connection), await records(connection)

        refused = alembic("upgrade", "heads")
        assert refused.returncode != 0 and "mystery" in refused.stderr, refused.stderr
        async with engine.connect() as connection:
            assert (await secrets(connection), await records(connection)) == before
        print("PASS a key under a name that is no provider stops the upgrade, unchanged")

        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM ln_secrets WHERE id = :id"), {"id": mystery[0]}
            )
        upgraded = alembic("upgrade", "heads")
        assert upgraded.returncode == 0, upgraded.stderr
        async with engine.connect() as connection:
            after, routed = await secrets(connection), await records(connection)
        assert not [key for key in after if key[0] == "provider"], after
        assert after[("workspace", "OPENAI_API_KEY")] == openai
        assert routed["openai"] == {"secret_id": openai[0], "url": None}
        assert old_anthropic[0] not in {row_id for row_id, _ in after.values()}
        assert after[("workspace", "ANTHROPIC_API_KEY")] == card_anthropic
        assert routed["anthropic"] == {"secret_id": card_anthropic[0], "url": None}
        assert after[("workspace", "DEEPSEEK_API_KEY")] == (card_deepseek[0], new_deepseek[1])
        assert new_deepseek[0] not in {row_id for row_id, _ in after.values()}
        assert routed["deepseek"] == {"secret_id": card_deepseek[0], "url": None}
        assert after[("workspace", "ZAI_API_KEY")] == own_zai
        assert after[("workspace", "ZAI_API_KEY_2")] == zai
        assert routed["zai"] == {"secret_id": zai[0], "url": None}
        print("PASS each key moves to the card's record as its ciphertext, the newest kept")

        try:
            async with engine.begin() as connection:
                await secret(connection, owner, "provider", "openrouter", later)
            raise AssertionError("a provider-scope key was stored")
        except IntegrityError:
            pass
        print("PASS no provider scope remains, and a new one is refused")

        back = alembic("downgrade", BEFORE)
        assert back.returncode == 0, back.stderr
        async with engine.connect() as connection:
            assert (await secrets(connection), await records(connection)) == (after, routed)
        assert alembic("upgrade", "heads").returncode == 0
        print("PASS the downgrade keeps every key where the earlier release reads it")
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM ln_settings WHERE key LIKE :prefix"), {"prefix": RECORD + "%"}
            )
            await connection.execute(
                text("DELETE FROM ln_secrets WHERE name LIKE '%_API_KEY%'"),
            )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
