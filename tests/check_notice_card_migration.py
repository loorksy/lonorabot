"""0088: the notice cards end (mandate 10.3.2, 14.2.7, 14.3.9).

On a disposable PostgreSQL already at head: step down below 0088 and seed an owner's
``watch_changed`` notices (a pending one, an older one it superseded, and one the owner
undid) and a settled ``stop_tightened`` notice next to a pending ``settle_operation``
card and a pending ``secret`` card. Upgrade and check that every notice is gone and the
other two cards are untouched. The downgrade restores nothing and the upgrade runs again
cleanly.
"""

import asyncio
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from check_streaming import test_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
BEFORE = "0101_settle_operation_card"


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)


async def cards(connection: AsyncConnection, owner: str) -> dict[str, tuple[Any, ...]]:
    rows = await connection.execute(
        text(
            "SELECT id, kind, subject, status, payload_hash FROM ln_owner_actions"
            " WHERE owner_id = :o"
        ),
        {"o": owner},
    )
    return {row.id: (row.kind, row.subject, row.status, row.payload_hash) for row in rows}


async def main() -> None:
    engine = create_async_engine(test_settings().database_url)
    now = datetime.now(UTC)
    ids = {
        name: str(uuid4())
        for name in (
            "owner",
            "agent",
            "watch_pending",
            "watch_superseded",
            "watch_undone",
            "stop",
            "settle",
            "secret",
        )
    }
    seeded: list[tuple[str, str, str, str, str | None]] = [
        ("watch_pending", "watch_changed", "watch:w1", "pending", None),
        ("watch_superseded", "watch_changed", "watch:w1", "superseded", "watch_pending"),
        ("watch_undone", "watch_changed", "watch:w2", "confirmed", None),
        ("stop", "stop_tightened", "position:a1:t1", "confirmed", None),
        ("settle", "settle_operation", "operation:op1", "pending", None),
        ("secret", "secret", "secret:workspace", "pending", None),
    ]
    kept = {
        ids["settle"]: ("settle_operation", "operation:op1", "pending", "hash"),
        ids["secret"]: ("secret", "secret:workspace", "pending", "hash"),
    }
    try:
        await asyncio.to_thread(alembic, "downgrade", BEFORE)
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO ln_owners (id, singleton, email, password_hash, created_at)"
                    " VALUES (:owner, 1, 'notice-cards-removal@example.com', 'x', :now)"
                ),
                {**ids, "now": now},
            )
            for name, kind, subject, status, superseded_by in seeded:
                await connection.execute(
                    text(
                        "INSERT INTO ln_owner_actions (id, owner_id, agent_id, source, kind,"
                        " subject, payload, payload_hash, status, superseded_by, expires_at,"
                        " created_at, updated_at) VALUES (:id, :owner, :agent, 'system', :kind,"
                        " :subject, '{}', 'hash', :status, :superseded_by, :expires, :now, :now)"
                    ),
                    {
                        **ids,
                        "id": ids[name],
                        "kind": kind,
                        "subject": subject,
                        "status": status,
                        "superseded_by": ids[superseded_by] if superseded_by else None,
                        "expires": now + timedelta(days=7),
                        "now": now,
                    },
                )
        await engine.dispose()

        await asyncio.to_thread(alembic, "upgrade", "heads")
        async with engine.connect() as connection:
            assert await cards(connection, ids["owner"]) == kept
        await engine.dispose()
        print("PASS every watch_changed and stop_tightened notice is deleted; other cards stay")

        await asyncio.to_thread(alembic, "downgrade", BEFORE)
        async with engine.connect() as connection:
            assert await cards(connection, ids["owner"]) == kept
        await engine.dispose()
        await asyncio.to_thread(alembic, "upgrade", "heads")
        async with engine.begin() as connection:
            assert await cards(connection, ids["owner"]) == kept
            await connection.execute(text("DELETE FROM ln_owners WHERE id = :owner"), ids)
        print("PASS the downgrade restores nothing; the upgrade repeats cleanly")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
