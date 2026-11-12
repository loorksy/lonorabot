"""Migration 0173: a stored reach-me preference of "activity only" becomes "message".

PostgreSQL only (LONORA_DATABASE_URL): downgrade below 0173, store the old choice,
upgrade, and read the preference through its contract again. An owner-preference
revision that names the old choice is rewritten too, so undoing it still works.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from check_streaming import Fixture
from lonora_contracts.incoming_calls import IncomingCallPolicy
from lonora_db.memory_revisions import record_revision
from lonora_db.owner_profile import (
    REACH_ME_KEY,
    preferences_snapshot,
    reach_me_policy,
    revert_revision,
)
from lonora_db.schema import MemoryRevisionRow
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
        # A change from "activity only" to "notify", stored before the choice was removed.
        after = preferences_snapshot(IncomingCallPolicy(channel="notify"), None)
        before = json.loads(after)
        before["reach_me"]["channel"] = "activity"
        async with fixture.runtime.db.sessions() as session, session.begin():
            revision = await record_revision(
                session,
                fixture.owner,
                document="owner_preferences",
                agent_id=None,
                version=None,
                previous_content=json.dumps(before, sort_keys=True, ensure_ascii=False),
                content=after,
                author="owner",
                change="preferences",
            )
            revision_id = revision.id
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
        async with fixture.runtime.db.sessions() as session:
            stored = await session.get(MemoryRevisionRow, revision_id)
            assert stored is not None
            previous, content = json.loads(stored.previous_content), json.loads(stored.content)
        assert previous["reach_me"]["channel"] == "message", previous
        assert content["reach_me"]["channel"] == "notify", content
        assert stored.content == after, "an untouched side keeps its exact text"
        # Undoing that change validates and restores the default, never "activity".
        async with fixture.runtime.db.sessions() as session, session.begin():
            await session.execute(
                text("UPDATE ln_settings SET payload = CAST(:payload AS JSON) WHERE key = :key"),
                {
                    "key": key,
                    "payload": json.dumps(
                        IncomingCallPolicy(channel="notify").model_dump(mode="json")
                    ),
                },
            )
        async with fixture.runtime.db.sessions() as session, session.begin():
            await revert_revision(session, fixture.owner, revision_id)
        async with fixture.runtime.db.sessions() as session:
            policy = await reach_me_policy(session, fixture.owner, fresh=True)
        assert policy.channel == "message", policy
        print("PASS a stored 'activity only' preference change is rewritten and can be undone")
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
