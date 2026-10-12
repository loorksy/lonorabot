import json

from lonora_db.schema import GroupRow
from sqlalchemy.ext.asyncio import AsyncSession


async def group_context(session: AsyncSession, group_id: str | None) -> str:
    if not group_id:
        return ""
    group = await session.get(GroupRow, group_id)
    return "<group>" + json.dumps(group.payload, ensure_ascii=False) + "</group>" if group else ""
