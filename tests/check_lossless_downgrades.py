"""Wave 1.5 downgrades lose nothing the owner decided, on disposable PostgreSQL.

Review regressions (durability lens):

- ``0039`` keeps the owner profile: lines the owner wrote after the upgrade are written
  back as the Personal Agent's ``# USER.md`` section before the tables go, and the
  re-upgrade merges them into the profile again.
- ``0042`` refuses while the owner's own choice would be lost and the re-upgrade would
  silently restore a default: a removed github.com (Skill imports from all of GitHub
  trusted again). The refused downgrade changes nothing. (Supervision grants are gone
  at head since ``0127``, so no revoked grant is left for ``0041`` to guard.)
- ``0043`` refuses while the owner holds a pause on an agent's work.
- ``0039``'s merge never pushes legacy preferences past the profile limit: whole agent
  blocks fit oldest first, and the rest goes to that agent's own operating notes.
"""

import asyncio
import importlib.util
import subprocess
import sys
from pathlib import Path
from typing import Any

from check_streaming import Fixture
from lonora_contracts.domain import utcnow
from lonora_contracts.routines import RoutineCreate
from lonora_db.personal_agent import ensure_personal_agent
from lonora_db.routines import create_routine
from lonora_db.schema import MemoryRow, TrustedSourceRow
from lonora_db.trusted_sources import ensure_defaults
from sqlalchemy import select
from sqlalchemy.ext.asyncio import create_async_engine

ROOT = Path(__file__).resolve().parents[1]
ALEMBIC = [sys.executable, "-m", "alembic", "-c", "packages/db/alembic.ini"]
MARKER = "Never trade during NFP; reply in Arabic. MARKER-7731"


def migration() -> Any:
    path = ROOT / "packages/db/migrations/versions/0039_owner_profile_memory_revisions.py"
    spec = importlib.util.spec_from_file_location("profile_migration", path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def alembic(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [*ALEMBIC, *arguments], capture_output=True, text=True, cwd=ROOT, check=False
    )


def current() -> str:
    return alembic("current").stdout.strip()


async def reopen(fixture: Fixture) -> Fixture:
    await fixture.runtime.db.close()
    return await Fixture().open()


async def main() -> None:
    fixture = await Fixture().open()
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            lonora_id = (await ensure_personal_agent(session, fixture.owner)).id
            await ensure_defaults(session, fixture.owner)
        private = await fixture.agent("Private")
        head = current()
        assert "(head)" in head, head

        # 1. The owner's profile survives a downgrade below 0039 and comes back.
        profile = await fixture.request("GET", "/owner/profile")
        saved = await fixture.request(
            "PUT", "/owner/profile", {"content": MARKER, "version": profile["version"]}
        )
        assert MARKER in saved["content"], saved
        await fixture.runtime.db.close()
        result = alembic("downgrade", "0038_owner_actions")
        assert result.returncode == 0, result.stderr[-2000:]
        fixture = await Fixture().open()
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(MemoryRow, lonora_id)
            assert row is not None and "# USER.md" in row.content and MARKER in row.content
        await fixture.runtime.db.close()
        result = alembic("upgrade", "head")
        assert result.returncode == 0, result.stderr[-2000:]
        fixture = await Fixture().open()
        restored = await fixture.request("GET", "/owner/profile")
        assert MARKER in restored["content"], restored
        print(
            "PASS a downgrade below 0039 keeps the owner's profile in Lonora's USER.md and the re-upgrade merges it back"
        )

        # 2. A removed github.com refuses the downgrade.
        async with fixture.runtime.db.sessions() as session:
            github = await session.scalar(
                select(TrustedSourceRow).where(
                    TrustedSourceRow.owner_id == fixture.owner,
                    TrustedSourceRow.identifier == "github.com",
                    TrustedSourceRow.revoked_at.is_(None),
                )
            )
        assert github is not None
        # The removed github.com: 0042 refuses.
        await fixture.request("POST", f"/trusted-sources/{github.id}/revoke")
        fixture = await reopen(fixture)
        refused: Any = alembic("downgrade", "0041_supervision_grants")
        assert refused.returncode != 0 and "trusted sources" in refused.stderr, refused.stderr
        assert current() == head, current()
        print(
            "PASS a downgrade below 0042 refuses while a removed source would come back as a default, and changes nothing"
        )

        # 3. The owner's own pause on an agent's work refuses a downgrade below 0043.
        async with fixture.runtime.db.sessions() as session, session.begin():
            routine = await create_routine(
                session,
                fixture.owner,
                private["id"],
                RoutineCreate(prompt="Review gold", interval_seconds=3600),
            )
            routine_id = routine.id
        await fixture.request(
            "PUT",
            f"/routines/{routine_id}",
            {"prompt": "Review gold", "interval_seconds": 3600, "enabled": False},
        )
        fixture = await reopen(fixture)
        refused = alembic("downgrade", "0042_trusted_sources")
        assert refused.returncode != 0 and "pause" in refused.stderr, refused.stderr
        assert current() == head, current()
        print("PASS a downgrade below 0043 refuses while the owner holds a pause")

        # 4. A legacy merge past the profile limit routes the overflow, never drops it.
        legacy = [await fixture.agent("Legacy " + str(index)) for index in range(3)]
        async with fixture.runtime.db.sessions() as session, session.begin():
            for index, agent in enumerate(legacy):
                row = await session.get(MemoryRow, agent["id"])
                assert row is not None
                lines = "\n".join(
                    f"- L{index} preference {line}: keep stops at structure ({index}-{line})"
                    for line in range(60)
                )
                row.content = "# USER.md\n" + lines + "\n# MEMORY.md\n- private note\n"
        module = migration()
        engine = create_async_engine(fixture.settings.database_url)
        try:
            async with engine.begin() as connection:
                changed = await connection.run_sync(
                    lambda sync: module.merge_owner(sync, fixture.owner, utcnow())
                )
            assert changed
            async with engine.begin() as connection:
                again = await connection.run_sync(
                    lambda sync: module.merge_owner(sync, fixture.owner, utcnow())
                )
            assert not again  # Idempotent: nothing moves twice.
        finally:
            await engine.dispose()
        merged = await fixture.request("GET", "/owner/profile")
        assert len(merged["content"]) <= module.PROFILE_LIMIT, len(merged["content"])
        routed = 0
        async with fixture.runtime.db.sessions() as session:
            for index, agent in enumerate(legacy):
                row = await session.get(MemoryRow, agent["id"])
                assert row is not None
                line = f"- L{index} preference 59: keep stops at structure ({index}-59)"
                in_profile = line in merged["content"]
                in_notes = module.OVERFLOW_HEADING in row.content and line in row.content
                assert in_profile or in_notes, index
                routed += in_notes
        assert routed >= 1
        # An over-limit profile (an older merge) can still be saved shorter by the owner,
        # and nothing grows past the limit: the refusal has a code with owner text.
        from lonora_db.schema import OwnerProfileRow

        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(OwnerProfileRow, fixture.owner)
            assert row is not None
            row.content = "- " + "x" * 9000 + "\n"
            version = row.version
        shorter = await fixture.client.put(
            "/api/owner/profile", json={"content": "- " + "x" * 8500 + "\n", "version": version}
        )
        assert shorter.status_code == 200, shorter.text
        longer = await fixture.client.put(
            "/api/owner/profile",
            json={"content": "- " + "x" * 8600 + "\n", "version": shorter.json()["version"]},
        )
        assert longer.status_code == 413 and longer.json()["code"] == "owner_profile_too_large"
        print(
            "PASS a legacy merge past the profile limit keeps whole agent blocks and routes the rest to that agent's operating notes, once; an over-limit profile saves shorter"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
