from typing import Any

from lonora_contracts.runs import Lease
from lonora_db.client import Database
from lonora_db.memory import commit_memory
from lonora_db.runs import require_lease

from .edits import MemoryEdit, apply_edits
from .markdown_memory import normalize_memory


async def atomic_commit(
    db: Database,
    owner_id: str,
    agent_id: str,
    content: str,
    version: int,
    *,
    lease: Lease | None = None,
    effect_key: str | None = None,
) -> dict[str, Any]:
    async with db.sessions() as session, session.begin():
        if lease:
            await require_lease(session, lease, lock=True)
        return await commit_memory(
            session,
            owner_id,
            agent_id,
            normalize_memory(content),
            version,
            effect_key,
            source_run_id=lease.run_id if lease else None,
        )


async def atomic_edit(
    db: Database,
    owner_id: str,
    agent_id: str,
    edits: list[MemoryEdit],
    version: int,
    *,
    lease: Lease | None = None,
    effect_key: str | None = None,
) -> dict[str, Any]:
    """Apply a batch of operations to the locked current revision, or nothing.

    The same receipt, lease fence and optimistic revision as a whole-document
    write; MemoryEditError and MemoryOverflow roll the transaction back.
    """

    def transform(current: str, current_version: int) -> tuple[str, dict[str, Any]]:
        content, applied = apply_edits(current, edits, current_version)
        return content, {"applied": applied}

    async with db.sessions() as session, session.begin():
        if lease:
            await require_lease(session, lease, lock=True)
        return await commit_memory(
            session,
            owner_id,
            agent_id,
            "",
            version,
            effect_key,
            source_run_id=lease.run_id if lease else None,
            transform=transform,
        )
