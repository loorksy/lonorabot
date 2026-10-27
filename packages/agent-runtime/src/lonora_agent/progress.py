from typing import Any

from lonora_contracts.domain import utcnow
from lonora_db.events import emit
from lonora_db.rich_response import validated_rich_content
from lonora_db.runs import require_lease
from lonora_db.streaming import append_rich_partial, append_stream, start_stream, stream_identity
from lonora_security.secrets import redact
from lonora_tools.context import ToolContext

DELTA_CHUNK_CHARS = 1024


async def progress(context: ToolContext, kind: str, payload: dict[str, Any]) -> None:
    async with context.db.sessions() as session, session.begin():
        row = await require_lease(session, context.lease, lock=True)
        payload = redact(payload)
        if kind in {
            "run.context_started",
            "run.reply_started",
            "run.delta",
            "run.rich_partial",
            "tool.started",
            "tool.completed",
            "tool.failed",
            "tool.cancelled",
        }:
            # Reconnection can project the actual latest activity without
            # replaying the entire token/tool history. This shares the existing
            # event transaction: no status request, model call or extra commit.
            row.model_metadata = {
                **row.model_metadata,
                "activity": {
                    "kind": kind,
                    "name": payload.get("name"),
                    "observed_at": utcnow().isoformat(),
                },
            }
        turn_id = payload.get("turn_id")
        if kind == "run.reply_started" and isinstance(turn_id, str):
            payload = {**payload, **stream_identity(start_stream(row, context.lease, turn_id))}
        elif kind == "run.delta" and isinstance(turn_id, str):
            # The model boundary admits complete safe prose/components. Provider
            # token sizes must not turn that projection into hundreds of writes.
            # Redact before splitting so a secret cannot cross a chunk boundary.
            accepted = str(payload.get("text", ""))
            compiled = validated_rich_content(payload.get("rich_content"))
            base = {key: value for key, value in payload.items() if key != "rich_content"}
            if not accepted and compiled is not None:
                stream = append_rich_partial(row, context.lease, turn_id, compiled)
                assert stream is not None
                emit(
                    session,
                    context.owner_id,
                    "run.rich_partial",
                    thread_id=context.thread_id,
                    agent_id=context.agent_id,
                    run_id=context.lease.run_id,
                    payload={**base, **stream_identity(stream)},
                )
            for offset in range(0, len(accepted), DELTA_CHUNK_CHARS):
                # Attach the cumulative UI once its accompanying text is fully
                # present. Later text-only deltas do not retransmit that tree.
                include_rich = compiled is not None and offset + DELTA_CHUNK_CHARS >= len(accepted)
                stream, text = append_stream(
                    row,
                    context.lease,
                    turn_id,
                    accepted[offset : offset + DELTA_CHUNK_CHARS],
                    **({"rich_content": compiled} if include_rich else {}),
                )
                emit(
                    session,
                    context.owner_id,
                    kind,
                    thread_id=context.thread_id,
                    agent_id=context.agent_id,
                    run_id=context.lease.run_id,
                    payload={
                        **base,
                        **stream_identity(stream, include_rich=include_rich),
                        "text": text,
                    },
                )
            return
        elif kind == "run.rich_partial" and isinstance(turn_id, str):
            compiled = validated_rich_content(payload.get("rich_content"))
            if compiled is None:
                return
            stream = append_rich_partial(row, context.lease, turn_id, compiled)
            assert stream is not None
            payload = {**payload, **stream_identity(stream)}
        emit(
            session,
            context.owner_id,
            kind,
            thread_id=context.thread_id,
            agent_id=context.agent_id,
            run_id=context.lease.run_id,
            payload=payload,
        )
