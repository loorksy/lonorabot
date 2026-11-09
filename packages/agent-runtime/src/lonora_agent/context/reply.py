from lonora_core.message_quote import quote
from lonora_db.schema import MessageRow
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession


async def reply_context(session: AsyncSession, thread_id: str, input_seq: int) -> str:
    message = await session.scalar(
        select(MessageRow).where(MessageRow.thread_id == thread_id, MessageRow.seq == input_seq)
    )
    if not message or not message.reply_to:
        return ""
    reply = await session.get(MessageRow, message.reply_to)
    # Raw quote: the builder labels and escapes it as conversation context data.
    return quote(reply.content) if reply and reply.thread_id == thread_id else ""
