from lonora_db.schema import MemoryRow
from lonora_memory.markdown_memory import memory_context
from sqlalchemy.ext.asyncio import AsyncSession


async def read_memory_context(session: AsyncSession, agent_id: str) -> str:
    row = await session.get(MemoryRow, agent_id)
    return memory_context(row.content) if row else ""
