"""Migration 0072 (signing in to an MCP server) downgrades without leaving rows behind.

The earlier release reads every stored MCP server through a contract that forbids
unknown fields, and this release stores ``oauth`` on every server, empty unless Lonora
signed in to it. On a disposable PostgreSQL at head: a sign-in the owner started, a
server with its address typed and a server Lonora signed in to. The downgrade refuses
while the signed-in server exists, and changes nothing. Once it is removed, the
downgrade drops the sign-ins and leaves the other server with exactly the fields it had,
less ``oauth``; the upgrade runs again and the new contract reads the row.
"""

import asyncio
import json
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from check_streaming import test_settings
from lonora_contracts.mcp import McpConnection, McpOAuth
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
BEFORE = "0072_mcp_sign_in-1"


def alembic(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run([*ALEMBIC, *arguments], capture_output=True, text=True, check=False)


def current() -> str:
    return alembic("current").stdout.strip()


async def server(connection: AsyncConnection, owner_id: str, config: McpConnection) -> str:
    row_id = str(uuid4())
    await connection.execute(
        text(
            "INSERT INTO ln_mcp_connections (id, owner_id, payload, state, version,"
            " created_at, updated_at) VALUES (:id, :owner, :payload, '{}', 1, :now, :now)"
        ),
        {
            "id": row_id,
            "owner": owner_id,
            "payload": json.dumps(config.model_dump(mode="json")),
            "now": datetime.now(UTC),
        },
    )
    return row_id


async def payload(connection: AsyncConnection, row_id: str) -> Any:
    raw = await connection.scalar(
        text("SELECT payload::text FROM ln_mcp_connections WHERE id = :id"), {"id": row_id}
    )
    return json.loads(raw or "null")


async def sign_ins(connection: AsyncConnection) -> bool:
    return bool(await connection.scalar(text("SELECT to_regclass('ln_mcp_sign_ins') IS NOT NULL")))


async def main() -> None:
    url = test_settings().database_url
    assert alembic("upgrade", "head").returncode == 0
    head = current()
    engine = create_async_engine(url)
    now = datetime.now(UTC)
    typed = McpConnection(name="Files", url="https://mcp.example.com/mcp")
    signed_in = McpConnection(
        name="Desk",
        url_secret_id=str(uuid4()),
        endpoint_sha256="0" * 64,
        secret_id=str(uuid4()),
        oauth=McpOAuth(
            issuer="https://auth.example.com",
            token_endpoint="https://auth.example.com/token",
            client_id="lonora",
            refresh_secret_id=str(uuid4()),
        ),
    )
    try:
        async with engine.begin() as connection:
            owner_id = await connection.scalar(text("SELECT id FROM ln_owners LIMIT 1")) or str(
                uuid4()
            )
            await connection.execute(
                text(
                    "INSERT INTO ln_owners (id, singleton, email, password_hash, created_at)"
                    " VALUES (:id, 1, 'mcp-sign-in-migration@example.com', 'x', :now)"
                    " ON CONFLICT DO NOTHING"
                ),
                {"id": owner_id, "now": now},
            )
            agent_id, card_id = str(uuid4()), str(uuid4())
            await connection.execute(
                text(
                    "INSERT INTO ln_agents (id, owner_id, name, avatar, color, instructions,"
                    " paused, created_at) VALUES (:id, :owner, 'mcp-sign-in', '', '', '', false,"
                    " :now)"
                ),
                {"id": agent_id, "owner": owner_id, "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO ln_owner_actions (id, owner_id, agent_id, source, kind, subject,"
                    " payload, payload_hash, status, result, expires_at, created_at, updated_at)"
                    " VALUES (:id, :owner, :agent, 'agent', 'secret', :id, '{}', :id, 'pending',"
                    " '{}', :expires, :now, :now)"
                ),
                {
                    "id": card_id,
                    "owner": owner_id,
                    "agent": agent_id,
                    "expires": now + timedelta(days=1),
                    "now": now,
                },
            )
            await connection.execute(
                text(
                    "INSERT INTO ln_mcp_sign_ins (id, owner_id, card_id, state_sha256, plan,"
                    " ciphertext, expires_at, created_at) VALUES (:id, :owner, :card,"
                    " :state, '{}', 'sealed', :expires, :now)"
                ),
                {
                    "id": str(uuid4()),
                    "owner": owner_id,
                    "card": card_id,
                    "state": uuid4().hex * 2,
                    "expires": now + timedelta(minutes=10),
                    "now": now,
                },
            )
            typed_id = await server(connection, owner_id, typed)
            signed_in_id = await server(connection, owner_id, signed_in)
            saved = await payload(connection, typed_id)
        assert saved["oauth"] is None, saved

        refused = alembic("downgrade", BEFORE)
        assert refused.returncode != 0 and "signed in with OAuth" in refused.stderr, refused.stderr
        assert current() == head
        async with engine.connect() as connection:
            assert await payload(connection, typed_id) == saved
            assert (await payload(connection, signed_in_id))["oauth"] is not None
            assert await sign_ins(connection)
        print("PASS the downgrade refuses while a server Lonora signed in to exists, unchanged")

        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM ln_mcp_connections WHERE id = :id"), {"id": signed_in_id}
            )
        downgraded = alembic("downgrade", BEFORE)
        assert downgraded.returncode == 0, downgraded.stderr
        async with engine.connect() as connection:
            earlier = await payload(connection, typed_id)
            assert not await sign_ins(connection)
        assert earlier == {key: value for key, value in saved.items() if key != "oauth"}, earlier
        print("PASS the downgrade drops the sign-ins and leaves the other server without oauth")

        assert alembic("upgrade", "head").returncode == 0
        assert current() == head
        async with engine.connect() as connection:
            McpConnection.model_validate(await payload(connection, typed_id))
            assert await sign_ins(connection)
        print("PASS the upgrade runs again and the new contract reads the row")
        async with engine.begin() as connection:
            await connection.execute(
                text("DELETE FROM ln_mcp_connections WHERE id = :id"), {"id": typed_id}
            )
            await connection.execute(text("DELETE FROM ln_agents WHERE id = :id"), {"id": agent_id})
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
