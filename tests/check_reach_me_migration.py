"""Migration 0173: a stored reach-me preference of "activity only" becomes "message".

PostgreSQL only (LONORA_DATABASE_URL): downgrade below 0173, store the old choice,
upgrade, and read the preference through its contract again.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from check_streaming import Fixture
from lonora_db.owner_profile import REACH_ME_KEY, reach_me_policy
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = "0138_skill_package_files"


def alembic(action: str, revision: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini", action, revision],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        env={**os.environ},
    )


async def main() -> None:
    fixture = await Fixture().open()
    try:
        key = REACH_ME_KEY + fixture.owner
        await asyncio.to_thread(alembic, "downgrade", PREVIOUS)
        async with fixture.runtime.db.sessions() as session, session.begin():
            await session.execute(text("DELETE FROM ln_settings WHERE key = :key"), {"key": key})
            await session.execute(
                text(
                    "INSERT INTO ln_settings (key, payload, updated_at) "
                    "VALUES (:key, CAST(:payload AS JSON), now())"
                ),
                {
                    "key": key,
                    "payload": json.dumps(
                        {"channel": "activity", "quiet_start_hour": 22, "quiet_end_hour": 6}
                    ),
                },
            )
        await asyncio.to_thread(alembic, "upgrade", "head")
        async with fixture.runtime.db.sessions() as session:
            policy = await reach_me_policy(session, fixture.owner, fresh=True)
        assert policy.channel == "message", policy
        assert (policy.quiet_start_hour, policy.quiet_end_hour) == (22, 6)
        print("PASS migration 0173 turns a stored 'activity only' reach-me into 'message'")
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
