from typing import Any

from lonora_db.events import emit
from lonora_db.runs import require_lease
from lonora_db.streaming import append_stream, start_stream, stream_identity
from lonora_security.secrets import redact
from lonora_tools.context import ToolContext


async def progress(context: ToolContext, kind: str, payload: dict[str, Any]) -> None:
    async with context.db.sessions() as session, session.begin():
        row = await require_lease(session, context.lease, lock=True)
        payload = redact(payload)
        turn_id = payload.get("turn_id")
        if kind == "run.reply_started" and isinstance(turn_id, str):
            payload = {**payload, **stream_identity(start_stream(row, context.lease, turn_id))}
        elif kind == "run.delta" and isinstance(turn_id, str):
            stream, text = append_stream(row, context.lease, turn_id, str(payload.get("text", "")))
            payload = {**payload, **stream_identity(stream), "text": text}
        emit(
            session,
            context.owner_id,
            kind,
            thread_id=context.thread_id,
            agent_id=context.agent_id,
            run_id=context.lease.run_id,
            payload=payload,
        )
