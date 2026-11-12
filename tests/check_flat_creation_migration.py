"""0125: Lonora creates agents with no card (mandate 3.1.2, 10.3, 14.3.9).

On a disposable PostgreSQL already at head: step down below 0125, seed an agent with a
pending ``create_agent`` card, an ``agent_created`` Undo card and a pending Mandate card,
upgrade and check that the two creation cards are deleted while the Mandate card and the
created agent stay; the upgrade runs again cleanly after a downgrade.
"""

import asyncio
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from check_streaming import test_settings
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
# 0125 merges the heads 0170 and 0061: downgrading to 0170 undoes 0125 alone.
BEFORE = "0170_broker_health_attention"


def alembic(*arguments: str) -> None:
    subprocess.run([*ALEMBIC, *arguments], check=True, capture_output=True, text=True)


async def cards(connection: AsyncConnection, owner: str) -> set[str]:
    rows = await connection.execute(
        text("SELECT kind FROM ln_owner_actions WHERE owner_id = :o"), {"o": owner}
    )
    return {row[0] for row in rows}


async def main() -> None:
    engine = create_async_engine(test_settings().database_url)
    now = datetime.now(UTC)
    ids = {name: str(uuid4()) for name in ("owner", "agent", "propose", "undo", "mandate")}
    try:
        await asyncio.to_thread(alembic, "downgrade", BEFORE)
        async with engine.begin() as connection:
            await connection.execute(
                text(
                    "INSERT INTO ln_owners (id, singleton, email, password_hash, created_at)"
                    " VALUES (:owner, 1, 'flat-creation@example.com', 'x', :now)"
                ),
                {**ids, "now": now},
            )
            await connection.execute(
                text(
                    "INSERT INTO ln_agents (id, owner_id, name, avatar, color, instructions,"
                    " paused, created_at) VALUES (:agent, :owner, 'Gold', '', '', '', false, :now)"
                ),
                {**ids, "now": now},
            )
            for card, kind, subject in (
                ("propose", "create_agent", "agent-create:x"),
                ("undo", "agent_created", "agent:" + ids["agent"]),
                ("mandate", "trading_mode", "trading_mode:" + ids["agent"]),
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
            assert await cards(connection, ids["owner"]) == {"trading_mode"}
            agent = await connection.scalar(
                text("SELECT count(*) FROM ln_agents WHERE id = :agent"), ids
            )
            assert agent == 1, agent
        await engine.dispose()
        print("PASS creation and Undo cards are deleted; the Mandate card and the agent stay")

        await asyncio.to_thread(alembic, "downgrade", BEFORE)
        await asyncio.to_thread(alembic, "upgrade", "heads")
        async with engine.begin() as connection:
            assert await cards(connection, ids["owner"]) == {"trading_mode"}
            await connection.execute(text("DELETE FROM ln_owners WHERE id = :owner"), ids)
        print("PASS the downgrade restores nothing; the upgrade repeats cleanly")
    finally:
        await engine.dispose()


if __name__ == "__main__":
    asyncio.run(main())
