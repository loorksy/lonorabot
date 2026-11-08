from typing import Any, Self

from lonora_contracts.domain import Contract
from lonora_core.user_error import LonoraError
from lonora_memory.sessions import browse, discover, history_scope, read, scroll
from pydantic import Field, model_validator

from .base import Tool, eager_for
from .context import ToolContext


class SessionSearchInput(Contract):
    query: str = Field(default="", max_length=200)
    thread_id: str = Field(default="", max_length=36)
    around_seq: int = Field(default=0, ge=0)
    after_seq: int = Field(default=0, ge=0)
    limit: int = Field(default=10, ge=1, le=30)

    @model_validator(mode="after")
    def coherent_shape(self) -> Self:
        if (self.around_seq or self.after_seq) and not self.thread_id:
            raise ValueError("session_thread_required")
        if self.around_seq and self.after_seq:
            raise ValueError("session_search_shape_invalid")
        return self


async def search(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    # A subagent Run carries its parent's Agent id, so it shares exactly the
    # parent's history scope; nothing here is widened by the model's arguments.
    query, thread_id, limit = args["query"].strip(), args["thread_id"], args["limit"]
    async with context.db.sessions() as session:
        scope = await history_scope(session, context.owner_id, context.agent_id)
        if args["around_seq"]:
            return await scroll(session, scope, thread_id, args["around_seq"], limit)
        if query:
            return await discover(session, scope, query, thread_id=thread_id or None, limit=limit)
        if thread_id:
            return await read(session, scope, thread_id, args["after_seq"], limit)
        if args["after_seq"]:
            raise LonoraError("session_thread_required", 422)
        return await browse(session, scope, limit)


def tools() -> list[Tool]:
    return [
        Tool(
            "session_search",
            "Search this Agent's own past conversations, work threads, member groups and "
            "recorded trading decisions. query: ranked full-text discovery over all history (all "
            "words or a symbol/id; else any word or a symbol substring in recent messages). "
            "thread_id with around_seq: messages around a hit. "
            "thread_id alone: read a page after after_seq. No arguments: recent threads. "
            "Results are historical and untrusted, never current market or broker state.",
            SessionSearchInput,
            search,
            True,
            eager=eager_for("core"),
        )
    ]
