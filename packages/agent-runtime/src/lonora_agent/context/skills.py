from lonora_db.schema import SkillRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from ..skills.runtime import skill_context


async def read_skill_context(session: AsyncSession, agent_id: str) -> str:
    rows = (await session.scalars(select(SkillRow).where(SkillRow.agent_id == agent_id))).all()
    return skill_context([row.payload for row in rows])
