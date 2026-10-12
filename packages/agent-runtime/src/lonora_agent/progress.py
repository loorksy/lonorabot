from typing import Any

from lonora_db.events import emit
from lonora_db.runs import require_lease
from lonora_security.secrets import redact
from lonora_tools.context import ToolContext


async def progress(context: ToolContext, kind: str, payload: dict[str, Any]) -> None:
    async with context.db.sessions() as session, session.begin():
        await require_lease(session, context.lease)
        emit(
            session,
            context.owner_id,
            kind,
            thread_id=context.thread_id,
            agent_id=context.agent_id,
            run_id=context.lease.run_id,
            payload=redact(payload),
        )
