from lonora_adapter_kit.types import ModelMessage
from lonora_db.schema import MessageRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def history_context(
    session: AsyncSession, thread_id: str, input_seq: int, summary_seq: int = 0
) -> list[ModelMessage]:
    rows = (
        await session.scalars(
            select(MessageRow)
            .where(
                MessageRow.thread_id == thread_id,
                MessageRow.seq <= input_seq,
                MessageRow.seq > summary_seq,
                MessageRow.role.in_(["user", "assistant"]),
            )
            .order_by(MessageRow.seq.desc())
            .limit(100)
        )
    ).all()
    return [
        ModelMessage(role="user" if row.role == "user" else "assistant", content=row.content)
        for row in reversed(rows)
    ]
