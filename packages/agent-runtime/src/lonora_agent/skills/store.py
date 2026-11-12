"""An agent's private skill-package store: the files of its package versions
(skills/<id>/<version>/...), kept in ln_skill_package_files. Packages are the agent's own
(3.2.1); the owner's workspace is shared by every agent (7.1), so a package's files are
copied into the agent's home only to be run (`skills/<id>/<version>/` there)."""

from lonora_contracts.domain import utcnow
from lonora_db.schema import SkillPackageFileRow
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession


async def stored_files(session: AsyncSession, agent_id: str) -> dict[str, bytes]:
    rows = await session.execute(
        select(SkillPackageFileRow.path, SkillPackageFileRow.content).where(
            SkillPackageFileRow.agent_id == agent_id
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
