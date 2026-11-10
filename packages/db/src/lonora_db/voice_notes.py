"""Owner voice notes: the transcript lands outside the send request, then the Agent answers.

``send_message`` stores a voice note with an empty content, a ``voice`` part whose
transcript is ``pending`` and a pending receipt, and admits no Run. The Gateway's
``voice_notes`` step transcribes the audio and calls ``settle_voice_note``, which
writes the transcript (or marks it failed), emits ``message.updated`` and only then
admits the Runs the message asks for. Settling is idempotent: the pending receipt is
removed in the same transaction.
"""

from typing import Any

from lonora_contracts.domain import MessageCreate
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .messages import VOICE_NOTE_PENDING, admit_runs, message_data
from .rich_response import server_rich_content
from .schema import EffectReceiptRow, MessageRow, ThreadRow


async def pending_voice_notes(session: AsyncSession, owner_id: str) -> list[str]:
    """Message ids of the owner's voice notes still waiting for a transcript, oldest first."""
    rows = await session.scalars(
        select(EffectReceiptRow)
        .where(EffectReceiptRow.key.startswith(VOICE_NOTE_PENDING))
        .order_by(EffectReceiptRow.created_at)
        .limit(50)
    )
    return [row.result["message_id"] for row in rows if row.result.get("owner_id") == owner_id]


async def settle_voice_note(
    session: AsyncSession, owner_id: str, message_id: str, transcript: str | None
) -> dict[str, Any] | None:
    """Store the transcript (``None``: it failed) and admit the message's Runs, once."""
    pending = await session.get(EffectReceiptRow, VOICE_NOTE_PENDING + message_id)
    if pending is None or pending.result.get("owner_id") != owner_id:
        return None
    # Same lock order as send_message: the thread first.
    thread = await session.scalar(
        select(ThreadRow)
        .where(ThreadRow.id == pending.result["thread_id"], ThreadRow.owner_id == owner_id)
        .with_for_update()
    )
    if thread is None:
        # The conversation was deleted with its messages: nothing is left to settle.
        await session.delete(pending)
        return None
    pending = await session.get(
        EffectReceiptRow,
        VOICE_NOTE_PENDING + message_id,
        with_for_update=True,
        populate_existing=True,
    )
    message = await session.get(MessageRow, message_id, with_for_update=True)
    if pending is None:
        return None
    await session.delete(pending)
    if message is None or message.thread_id != thread.id:
        return None
    text = (transcript or "").strip()
    message.content = text
    message.rich_content = server_rich_content(
        *(
            {**part, "transcript_status": "done" if text else "failed"}
            if part.get("type") == "voice"
            else part
            for part in (message.rich_content or {}).get("parts", [])
        )
    )
    if not thread.title and text:
        thread.title = text[:80]
    data = message_data(message)
    # Clients see the transcript before the Run it starts.
    emit(session, owner_id, "message.updated", thread_id=thread.id, payload=data)
    reply = await session.get(MessageRow, message.reply_to) if message.reply_to else None
    request = MessageCreate.model_construct(
        content=text,
        client_nonce=message.client_nonce or message.id,
        reply_to=message.reply_to,
        attachment_ids=[],
        mention_agent_ids=[],
        mention_all=False,
        collaboration_session_id=None,
        input_answer=None,
        voice=None,
    )
    run_ids = await admit_runs(session, owner_id, thread, message, request, reply, None, None)
    receipt = await session.get(EffectReceiptRow, "message:" + message.id, with_for_update=True)
    if receipt is not None:
        receipt.result = {**receipt.result, "run_ids": run_ids}
    return data
