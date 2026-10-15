"""Speech interruption never means cancellation of durable agent work."""

from lonora_db.client import Database
from lonora_db.events import emit
from lonora_db.schema import VoiceSessionRow
from lonora_db.transactions import owned_thread
from sqlalchemy import select


async def barge_in(
    db: Database, owner_id: str, thread_id: str, *, session_id: str | None = None
) -> list[str]:
    async with db.sessions() as session, session.begin():
        await owned_thread(session, owner_id, thread_id)
        query = select(VoiceSessionRow).where(
            VoiceSessionRow.owner_id == owner_id,
            VoiceSessionRow.thread_id == thread_id,
            VoiceSessionRow.payload["status"].as_string() == "connected",
        )
        if session_id is not None:
            query = query.where(VoiceSessionRow.id == session_id)
        sessions = list(await session.scalars(query.with_for_update()))
        for voice in sessions:
            voice.state = {
                **voice.state,
                "speech_interrupt_requested": int(voice.state.get("speech_interrupt_requested", 0))
                + 1,
            }
            emit(
                session,
                owner_id,
                "voice.speech_interrupt_requested",
                thread_id=thread_id,
                agent_id=voice.agent_id,
                payload={"session_id": voice.id},
            )
    # Retain the existing response contract, explicitly reporting zero cancelled runs.
    return []
