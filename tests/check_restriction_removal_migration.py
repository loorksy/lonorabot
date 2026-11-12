"""0086: trading restrictions end (mandate 14.2.3, 14.3.9, 14.3.18.6).

On a disposable PostgreSQL already at head: step down below 0086, seed an agent the
owner paused, a pending ``lift_restriction`` card and a pending ``resume_trading`` card,
upgrade and check that the lift card is deleted, the other card stays, the owner's pause
stays and the restriction table is gone; the downgrade recreates the empty table and the
upgrade runs again cleanly.
"""

import asyncio
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from check_streaming import test_settings
from sqlalchemy import inspect, text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
BEFORE = "0085_opportunity_pending_operations"


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)


async def tables(connection: AsyncConnection) -> set[str]:
    return set(await connection.run_sync(lambda conn: inspect(conn).get_table_names()))


async def cards(connection: AsyncConnection, owner: str) -> set[str]:
    rows = await connection.execute(
        text("SELECT kind FROM ln_owner_actions WHERE owner_id = :o"), {"o": owner}
    )
    return {row[0] for row in rows}


async def main() -> None:
    engine = create_async_engine(test_settings().database_url)
    now = datetime.now(UTC)
    ids = {name: str(uuid4()) for name in ("owner", "agent", "lift", "resume")}
    try:
        await asyncio.to_thread(alembic, "downgrade", BEFORE)
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO ln_owners (id, singleton, email, password_hash, created_at)"
                    " VALUES (:owner, 1, 'restriction-removal@example.com', 'x', :now)"
                ),
                {**ids, "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO ln_agents (id, owner_id, name, avatar, color, instructions,"
                    " paused, created_at) VALUES (:agent, :owner, 'Gold', '', '', '', true, :now)"
                ),
                {**ids, "now": now},
            )
            for card, kind, subject in (
                ("lift", "lift_restriction", "restriction:r1"),
                ("resume", "resume_trading", "trading"),
            ):
                await connection.execute(
                    text(
                        "INSERT INTO ln_owner_actions (id, owner_id, agent_id, source, kind,"
                        " subject, payload, payload_hash, status, expires_at, created_at,"
                        " updated_at) VALUES (:id, :owner, :agent, 'system', :kind, :subject,"
                        " '{}', 'hash', 'pending', :expires, :now, :now)"
                    ),
                    {
                        **ids,
                        "id": ids[card],
                        "kind": kind,
                        "subject": subject,
                        "now": now,
                        "expires": now + timedelta(hours=1),
                    },
                )
        await engine.dispose()

        await asyncio.to_thread(alembic, "upgrade", "heads")
        async with engine.connect() as connection:
            assert await cards(connection, ids["owner"]) == {"resume_trading"}
            assert "ln_trading_restrictions" not in await tables(connection)
            paused = await connection.scalar(
                text("SELECT paused FROM ln_agents WHERE id = :agent"), ids
            )
            assert paused is True, paused
        await engine.dispose()
        print(
            "PASS lift_restriction cards are deleted, other cards and the owner's pause stay,"
            " the table is gone"
        )

        await asyncio.to_thread(alembic, "downgrade", BEFORE)
        async with engine.connect() as connection:
            assert "ln_trading_restrictions" in await tables(connection)
            count = await connection.scalar(text("SELECT count(*) FROM ln_trading_restrictions"))
            assert count == 0, count
        await engine.dispose()
        await asyncio.to_thread(alembic, "upgrade", "heads")
        async with engine.begin() as connection:
            assert "ln_trading_restrictions" not in await tables(connection)
            await connection.execute(text("DELETE FROM ln_owners WHERE id = :owner"), ids)
        print("PASS the downgrade recreates the empty table; the upgrade repeats cleanly")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
