"""Migration 0071 (the Secret card) leaves a downgraded release rows it can read.

The earlier release reads every stored MCP server and integration through contracts that
forbid unknown fields, and the new contracts store their added fields even when empty.
On a disposable PostgreSQL at head: save an MCP server and a news feed with their
addresses typed, as the new contracts store them, and an MCP server saved from a Secret
card. The downgrade refuses while that server's address is in the encrypted store, and
changes nothing. Once it is removed, the downgrade leaves each payload with exactly the
earlier release's fields and the same values, and the upgrade runs again cleanly.
"""

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from check_streaming import test_settings
from lonora_contracts.integrations import Integration
from lonora_contracts.mcp import McpConnection
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
BEFORE = "0071_secret_card_kinds-1"
SERVERS = "ln_mcp_connections"
INTEGRATIONS = "ln_integrations"
# The fields of the earlier release's contracts (main before 0071).
EARLIER = {
    SERVERS: {"name", "transport", "url", "command", "secret_id", "enabled"},
    INTEGRATIONS: {
        "type",
        "name",
        "url",
        "secret_id",
        "enabled",
        "thread_id",
        "deliver_to_agent_id",
        "allowed_destinations",
    },
}


def alembic(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*ALEMBIC, *arguments], capture_output=True, text=True, check=False)


def current() -> str:
    return alembic("current").stdout.strip()


async def insert(
    connection: AsyncConnection, table: str, owner_id: str, payload: dict[str, Any]
) -> str:
    row_id = str(uuid4())
    await connection.execute(
        text(
            f"INSERT INTO {table} (id, owner_id, payload, state, version, created_at,"
            " updated_at) VALUES (:id, :owner, :payload, '{}', 1, :now, :now)"
        ),
        {"id": row_id, "owner": owner_id, "payload": json.dumps(payload), "now": datetime.now(UTC)},
    )
    return row_id


async def stored(connection: AsyncConnection, rows: dict[str, str]) -> dict[str, Any]:
    """Each row's payload, by table."""
    found: dict[str, Any] = {}
    for table, row_id in rows.items():
        raw = await connection.scalar(
            text(f"SELECT payload::text FROM {table} WHERE id = :id"), {"id": row_id}
        )
        found[table] = json.loads(raw or "null")
    return found


async def main() -> None:
    url = test_settings().database_url
    assert alembic("upgrade", "head").returncode == 0
    head = current()
    engine = create_async_engine(url)
    server = McpConnection(name="Files", url="https://mcp.example.com/mcp")
    feed = Integration(type="news_feed", name="Wire", url="https://news.example.com/rss")
    vault = McpConnection(name="Vault", url_secret_id=str(uuid4()), endpoint_sha256="0" * 64)
    try:
        async with engine.begin() as connection:
            owner_id = await connection.scalar(text("SELECT id FROM ln_owners LIMIT 1")) or str(
                uuid4()
            )
            await connection.execute(
                text(
                    "INSERT INTO ln_owners (id, singleton, email, password_hash, created_at)"
                    " VALUES (:id, 1, 'secret-card-migration@example.com', 'x', :now)"
                    " ON CONFLICT DO NOTHING"
                ),
                {"id": owner_id, "now": datetime.now(UTC)},
            )
            rows = {
                SERVERS: await insert(
                    connection, SERVERS, owner_id, server.model_dump(mode="json")
                ),
                INTEGRATIONS: await insert(
                    connection, INTEGRATIONS, owner_id, feed.model_dump(mode="json")
                ),
            }
            vault_id = await insert(connection, SERVERS, owner_id, vault.model_dump(mode="json"))
        async with engine.connect() as connection:
            saved = await stored(connection, rows)
        assert "url_secret_id" in saved[SERVERS] and "domain" in saved[INTEGRATIONS], saved

        refused = alembic("downgrade", BEFORE)
        assert refused.returncode != 0 and "encrypted store" in refused.stderr, refused.stderr
        assert current() == head
        async with engine.connect() as connection:
            assert await stored(connection, rows) == saved
        print("PASS the downgrade refuses while a server's address is in the store, unchanged")

        async with engine.begin() as connection:
            await connection.execute(
                text(f"DELETE FROM {SERVERS} WHERE id = :id"), {"id": vault_id}
            )
        downgraded = alembic("downgrade", BEFORE)
        assert downgraded.returncode == 0, downgraded.stderr
        async with engine.connect() as connection:
            earlier = await stored(connection, rows)
        for table, payload in earlier.items():
            assert set(payload) == EARLIER[table], (table, sorted(payload))
            # 0200's downgrade gives servers back the fields the earlier contract had.
            restored = {"transport": "http", "command": None} if table == SERVERS else {}
            expected = {key: saved[table].get(key, restored.get(key)) for key in EARLIER[table]}
            assert payload == expected, table
        print("PASS the downgrade leaves every connection with exactly the earlier fields")

        assert alembic("upgrade", "head").returncode == 0
        assert current() == head
        async with engine.connect() as connection:
            again = await stored(connection, rows)
        McpConnection.model_validate(again[SERVERS])
        Integration.model_validate(again[INTEGRATIONS])
        print("PASS the upgrade runs again and the new contracts read the rows")
        async with engine.begin() as connection:
            for table, row_id in rows.items():
                await connection.execute(
                    text(f"DELETE FROM {table} WHERE id = :id"), {"id": row_id}
                )
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
