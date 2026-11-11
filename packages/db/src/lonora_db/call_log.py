"""Call log bubbles (Q34): a finished, declined or missed call as a system message.

The message lands in the Agent's canonical direct conversation with a ``call`` part.
It is a record only: role ``system`` never starts a Run and Agents never read it.
One message per call, whatever path or retry reports the call's end.
"""

from typing import Literal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .messages import message_data
from .rich_response import server_rich_content
from .schema import EffectReceiptRow, MessageRow, ThreadRow
from .threads import conversation_thread

CALL_TEXT = "مكالمة صوتية"
MISSED_CALL_TEXT = "مكالمة صوتية فائتة"


async def log_call(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    call_id: str,
    *,
    direction: Literal["outgoing", "incoming"],
    duration_seconds: int,
    missed: bool,
) -> MessageRow | None:
    """Write the call's bubble once; ``None`` when this call was already logged."""
    key = "call-log:" + call_id
    if await session.get(EffectReceiptRow, key):
        return None
    canonical = await conversation_thread(session, owner_id, agent_id)
    thread = await session.scalar(
        select(ThreadRow)
        .where(ThreadRow.id == canonical.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    )
    assert thread is not None
    if await session.get(EffectReceiptRow, key, populate_existing=True):
        return None
    message = MessageRow(
        thread_id=thread.id,
        agent_id=agent_id,
        seq=thread.next_seq,
        role="system",
        content=MISSED_CALL_TEXT if missed else CALL_TEXT,
        rich_content=server_rich_content(
            {
                "type": "call",
                "direction": direction,
                "duration_seconds": max(0, duration_seconds),
                "missed": missed,
            }
        ),
    )
    thread.next_seq += 1
    session.add(message)
    await session.flush()
    session.add(EffectReceiptRow(key=key, result={"message_id": message.id}))
    emit(
        session,
        owner_id,
        "message.created",
        thread_id=thread.id,
        agent_id=agent_id,
        payload=message_data(message),
    )
    return message
