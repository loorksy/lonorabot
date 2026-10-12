from typing import Any

from lonora_contracts.runs import Lease
from lonora_db.client import Database
from lonora_db.memory import commit_memory
from lonora_db.runs import require_lease

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
            session, owner_id, agent_id, normalize_memory(content), version, effect_key
        )
