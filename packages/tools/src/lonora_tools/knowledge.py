"""Knowledge notes from chat (mandate 13.1, P5).

The owner gives an agent a note in conversation; the agent adds, lists or removes it. An
agent manages its own notes; Lonora, the lead, manages any agent's (3.1.6, 3.2.4). Notes reach
recall as untrusted memory content, like every other note.
"""

from typing import Any

from lonora_contracts.domain import Contract
from lonora_core.user_error import LonoraError
from lonora_db.knowledge import knowledge_items
from lonora_db.schema import AgentRow, SemanticMemoryRow
from lonora_db.transactions import owned_agent
from lonora_memory.semantic import index_note
from pydantic import Field

from .base import Tool
from .context import ToolContext

AGENT = Field(default=None, max_length=36, description="Another agent's id; Lonora only.")


class NoteAdd(Contract):
    content: str = Field(min_length=1, max_length=8000)
    title: str | None = Field(default=None, max_length=160)
    replaces: str | None = Field(
        default=None, max_length=64, description="A note id this text replaces (an edit)."
    )
    agent_id: str | None = AGENT


class NoteList(Contract):
    agent_id: str | None = AGENT


class NoteDelete(Contract):
    note_id: str = Field(min_length=1, max_length=64)
    agent_id: str | None = AGENT


async def target(context: ToolContext, agent_id: str | None) -> str:
    """The agent whose notes are read or changed: the caller, or any agent for Lonora."""
    if agent_id is None or agent_id == context.agent_id:
        return context.agent_id
    async with context.db.sessions() as session:
        caller = await session.get(AgentRow, context.agent_id)
        if caller is None or caller.role != "personal":
            raise LonoraError("knowledge_note_agent_not_allowed", 403)
        await owned_agent(session, context.owner_id, agent_id)
    return agent_id


def refused(error: LonoraError) -> dict[str, Any]:
    return {"ok": False, "code": error.code}


async def add(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = NoteAdd.model_validate(args)
    try:
        agent_id = await target(context, params.agent_id)
        saved = await index_note(
            context.db,
            context.router.credentials,
            context.owner_id,
            agent_id,
            params.content,
            params.title,
            replaces=params.replaces,
        )
    except LonoraError as error:
        return refused(error)
    return {"ok": True, **saved}


async def listing(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = NoteList.model_validate(args)
    try:
        agent_id = await target(context, params.agent_id)
        async with context.db.sessions() as session:
            items = await knowledge_items(session, context.owner_id, agent_id)
    except LonoraError as error:
        return refused(error)
    return {"ok": True, "notes": [item for item in items if item["type"] == "note"]}


async def delete(context: ToolContext, args: dict[str, Any]) -> dict[str, Any]:
    params = NoteDelete.model_validate(args)
    try:
        agent_id = await target(context, params.agent_id)
        async with context.db.sessions() as session, session.begin():
            row = await session.get(SemanticMemoryRow, params.note_id)
            if row is None or row.owner_id != context.owner_id or row.agent_id != agent_id:
                raise LonoraError("knowledge_note_not_found", 404)
            await session.delete(row)
    except LonoraError as error:
        return refused(error)
    return {"ok": True, "deleted": True}


def tools() -> list[Tool]:
    return [
        Tool(
            "knowledge_note_add",
            "Save a knowledge note the owner gives in chat (a rule, a fact, a reference). "
            "Found later by its words; an embedding model, when set, also ranks it by meaning. "
            "Saving the same text again changes nothing; replaces edits an existing note.",
            NoteAdd,
            add,
        ),
        Tool(
            "knowledge_note_list",
            "List an agent's knowledge notes: id, title and text.",
            NoteList,
            listing,
            True,
        ),
        Tool(
            "knowledge_note_delete",
            "Remove one knowledge note by id when the owner asks.",
            NoteDelete,
            delete,
        ),
    ]
