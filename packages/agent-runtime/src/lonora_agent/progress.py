from typing import Any

from lonora_db.events import emit
from lonora_db.runs import require_lease
from lonora_db.streaming import append_stream, start_stream, stream_identity
from lonora_security.secrets import redact
from lonora_tools.context import ToolContext

DELTA_CHUNK_CHARS = 1024


async def progress(context: ToolContext, kind: str, payload: dict[str, Any]) -> None:
    async with context.db.sessions() as session, session.begin():
        row = await require_lease(session, context.lease, lock=True)
        payload = redact(payload)
        turn_id = payload.get("turn_id")
        if kind == "run.reply_started" and isinstance(turn_id, str):
            payload = {**payload, **stream_identity(start_stream(row, context.lease, turn_id))}
        elif kind == "run.delta" and isinstance(turn_id, str):
            # Publication happens only after the model's complete reply passes
            # its disclosure and execution-truth checks. Provider token sizes
            # must not turn that accepted reply into hundreds of transactions.
            # Redact before splitting so a secret cannot cross a chunk boundary.
            accepted = str(payload.get("text", ""))
            for offset in range(0, len(accepted), DELTA_CHUNK_CHARS):
                stream, text = append_stream(
                    row, context.lease, turn_id, accepted[offset : offset + DELTA_CHUNK_CHARS]
                )
                emit(
                    session,
                    context.owner_id,
                    kind,
                    thread_id=context.thread_id,
                    agent_id=context.agent_id,
                    run_id=context.lease.run_id,
                    payload={**payload, **stream_identity(stream), "text": text},
                )
            return
        emit(
            session,
            context.owner_id,
            kind,
            thread_id=context.thread_id,
            agent_id=context.agent_id,
            run_id=context.lease.run_id,
            payload=payload,
        )
