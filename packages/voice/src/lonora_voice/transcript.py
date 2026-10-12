from typing import Any

from lonora_contracts.domain import MessageCreate
from lonora_contracts.voice import VoiceTranscript
from lonora_db.client import Database
from lonora_db.messages import send_message


async def commit_transcript(
    db: Database, owner_id: str, thread_id: str, transcript: VoiceTranscript
) -> dict[str, Any]:
    if not transcript.final:
        return {"committed": False}
    async with db.sessions() as session, session.begin():
        return await send_message(
            session,
            owner_id,
            thread_id,
            MessageCreate(content=transcript.text, client_nonce="voice:" + transcript.client_nonce),
        )
