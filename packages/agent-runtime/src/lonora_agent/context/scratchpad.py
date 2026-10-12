from lonora_db.schema import ScratchpadRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def scratchpad_context(session: AsyncSession, agent_id: str) -> str:
    rows = (
        await session.scalars(
            select(ScratchpadRow)
            .where(ScratchpadRow.agent_id == agent_id)
            .order_by(ScratchpadRow.updated_at.desc())
            .limit(12)
        )
    ).all()
    notes = "\n".join(
        str(row.payload.get("title", "")) + ": " + str(row.payload.get("content", ""))
        for row in rows
    )
    return "<scratchpad>\n" + notes[:16000] + "\n</scratchpad>" if notes else ""
