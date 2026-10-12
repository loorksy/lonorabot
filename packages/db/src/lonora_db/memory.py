from typing import Any

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import EffectReceiptRow, MemoryRow
from .transactions import owned_agent


async def read_memory(session: AsyncSession, owner_id: str, agent_id: str) -> MemoryRow:
    await owned_agent(session, owner_id, agent_id)
    row = await session.get(MemoryRow, agent_id)
    if row is None:
        raise LonoraError("memory_not_found", 404)
    return row


def memory_data(row: MemoryRow) -> dict[str, Any]:
    return {
        "agent_id": row.agent_id,
        "content": row.content,
        "version": row.version,
        "updated_at": row.updated_at.isoformat(),
    }


async def commit_memory(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    content: str,
    expected_version: int,
    effect_key: str | None = None,
) -> dict[str, Any]:
    await owned_agent(session, owner_id, agent_id, lock=True)
    if effect_key:
        receipt = await session.get(EffectReceiptRow, effect_key)
        if receipt:
            return receipt.result
    row = await session.get(MemoryRow, agent_id, with_for_update=True)
    if row is None:
        raise LonoraError("memory_not_found", 404)
    if row.version != expected_version:
        raise LonoraError("version_conflict", 409)
    if len(content) > 30000:
        raise LonoraError("memory_too_large", 413)
    row.content = content
    row.version += 1
    row.updated_at = utcnow()
    result = memory_data(row)
    if effect_key:
        session.add(EffectReceiptRow(key=effect_key, result=result))
    emit(session, owner_id, "memory.updated", agent_id=agent_id, payload={"version": row.version})
    return result
