"""An agent's private skill-package store: the files of its package versions
(skills/<id>/<version>/...), kept in ln_skill_package_files. Packages are the agent's own
(3.2.1); the owner's workspace is shared by every agent (7.1), so a package's files are
copied into the agent's home only to be run (`skills/<id>/<version>/` there)."""

from collections.abc import Collection

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.schema import SkillPackageFileRow
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

# Every version of every package of one agent, together (a version holds at most 1 MiB).
STORE_BYTES = 64 * 1024 * 1024


async def stored_files(
    session: AsyncSession, agent_id: str, paths: Collection[str]
) -> dict[str, bytes]:
    """The stored bytes of these paths (a version's files); a missing path is absent."""
    if not paths:
        return {}
    rows = await session.execute(
        select(SkillPackageFileRow.path, SkillPackageFileRow.content).where(
            SkillPackageFileRow.agent_id == agent_id, SkillPackageFileRow.path.in_(list(paths))
        )
    )
    return {path: bytes(content) for path, content in rows.all()}


async def store_files(session: AsyncSession, agent_id: str, files: dict[str, str]) -> None:
    """Add a version's files, in the caller's transaction. Paths carry the version
    (skills/<id>/<version>/); a path stored again takes the new bytes."""
    if not files:
        return
    now = utcnow()
    statement = insert(SkillPackageFileRow).values(
        [
            {"agent_id": agent_id, "path": path, "content": body.encode(), "stored_at": now}
            for path, body in files.items()
        ]
    )
    await session.execute(
        statement.on_conflict_do_update(
            index_elements=["agent_id", "path"],
            set_={"content": statement.excluded.content, "stored_at": now},
        )
    )
    total = await session.scalar(
        select(func.coalesce(func.sum(func.length(SkillPackageFileRow.content)), 0)).where(
            SkillPackageFileRow.agent_id == agent_id
        )
    )
    # Refused inside the caller's transaction, so the version is not published either.
    if int(total or 0) > STORE_BYTES:
        raise LonoraError("skill_package_store_full", 413)


async def version_paths(session: AsyncSession, agent_id: str, directory: str) -> list[str]:
    """The stored paths under a version's directory (skills/<id>/<version>)."""
    prefix = directory.rstrip("/") + "/"
    rows = await session.scalars(
        select(SkillPackageFileRow.path).where(
            SkillPackageFileRow.agent_id == agent_id,
            func.substr(SkillPackageFileRow.path, 1, len(prefix)) == prefix,
        )
    )
    return list(rows.all())
