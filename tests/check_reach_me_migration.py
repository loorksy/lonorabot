"""Migration 0173: a stored reach-me preference of "activity only" becomes "message".

PostgreSQL only (LONORA_DATABASE_URL): downgrade below 0173, store the old choice,
upgrade, and read the preference through its contract again. The owner did not make
the move, so it is recorded once in his preference history as the system's change;
the history he wrote keeps "activity only" as he chose it, and undoing a change back
to it is refused with a reason.
"""

import asyncio
import json
import os
import subprocess
import sys
from pathlib import Path

from check_streaming import Fixture
from lonora_contracts.incoming_calls import IncomingCallPolicy
from lonora_core.user_error import LonoraError
from lonora_db.memory_revisions import list_revisions, record_revision
from lonora_db.owner_profile import (
    REACH_ME_KEY,
    preference_changes,
    preferences_snapshot,
    reach_me_policy,
    revert_revision,
)
from lonora_db.schema import MemoryRevisionRow
from sqlalchemy import text

ROOT = Path(__file__).resolve().parents[1]
PREVIOUS = "0088_end_notice_cards"


def alembic(action: str, revision: str) -> None:
    subprocess.run(
        [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini", action, revision],
        check=True,
        cwd=ROOT,
        stdout=subprocess.DEVNULL,
        env={**os.environ},
    )


async def refused(owner: str, revision_id: str, fixture: Fixture) -> str:
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            await revert_revision(session, owner, revision_id)
    except LonoraError as error:
        return error.code
    return "undone"


async def main() -> None:
    fixture = await Fixture().open()
    try:
        key = REACH_ME_KEY + fixture.owner
        # The owner's change from "activity only" to "notify", stored before the choice
        # was removed.
        after = preferences_snapshot(IncomingCallPolicy(channel="notify"), None)
        before = json.loads(after)
        before["reach_me"]["channel"] = "activity"
        owner_before = json.dumps(before, sort_keys=True, ensure_ascii=False)
        async with fixture.runtime.db.sessions() as session, session.begin():
            revision = await record_revision(
                session,
                fixture.owner,
                document="owner_preferences",
                agent_id=None,
                version=None,
                previous_content=owner_before,
                content=after,
                author="owner",
                change="preferences",
            )
            owner_revision = revision.id
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
            rows = await list_revisions(session, fixture.owner, ("owner_preferences",))
            stored = await session.get(MemoryRevisionRow, owner_revision)
            assert stored is not None
            kept = (stored.previous_content, stored.content, stored.version)
        moved = [row for row in rows if row.change == "choice_removed"]
        assert len(moved) == 1 and moved[0].author == "system", rows
        assert rows[0].id == moved[0].id and moved[0].version > kept[2], "the newest change"
        assert preference_changes(moved[0].previous_content, moved[0].content) == [
            {"field": "reach_me", "before": "activity", "after": "message"}
        ]
        assert kept[:2] == (owner_before, after), "the owner's own history is never rewritten"
        print("PASS the move is recorded once as the system's change; the owner's stays")
        for revision_id in (owner_revision, moved[0].id):
            assert await refused(fixture.owner, revision_id, fixture) == "reach_me_choice_removed"
        async with fixture.runtime.db.sessions() as session:
            policy = await reach_me_policy(session, fixture.owner, fresh=True)
            count = len(await list_revisions(session, fixture.owner, ("owner_preferences",)))
        assert policy.channel == "message" and count == len(rows), "nothing else was saved"
        print("PASS undoing a change back to 'activity only' is refused and saves nothing")
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
