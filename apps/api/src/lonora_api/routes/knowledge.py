"""«المعرفة» of one agent: its semantic notes and links as one list, and note edits."""

from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.knowledge import KnowledgeNote
from lonora_core.user_error import LonoraError
from lonora_db.knowledge import knowledge_items
from lonora_db.schema import SemanticMemoryRow
from lonora_db.transactions import owned_agent
from lonora_memory.semantic import index_note

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/agents/{agent_id}")


@router.get("/knowledge")
async def knowledge(
    request: Request, agent_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        return await knowledge_items(session, owner.id, agent_id)


@router.post("/knowledge/notes", status_code=201)
async def add_note(
    request: Request,
    agent_id: str,
    body: KnowledgeNote,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    rt = runtime(request)
    return await index_note(
        rt.db,
        rt.services(owner.id).router.credentials,
        owner.id,
        agent_id,
        body.content,
        body.title,
    )


@router.put("/knowledge/notes/{note_id}")
async def edit_note(
    request: Request,
    agent_id: str,
    note_id: str,
    body: KnowledgeNote,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    """A note is indexed by its text: new text is a new note that replaces the old one."""
    rt = runtime(request)
    async with rt.db.sessions() as session:
        await owned_note(session, owner.id, agent_id, note_id)
    result = await index_note(
        rt.db,
        rt.services(owner.id).router.credentials,
        owner.id,
        agent_id,
        body.content,
        body.title,
    )
    if result["id"] != note_id:
        async with rt.db.sessions() as session, session.begin():
            row = await session.get(SemanticMemoryRow, note_id, with_for_update=True)
            if row is not None:
                await session.delete(row)
    return result


@router.delete("/knowledge/notes/{note_id}")
async def delete_note(
    request: Request, agent_id: str, note_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    async with runtime(request).db.sessions() as session, session.begin():
        await session.delete(await owned_note(session, owner.id, agent_id, note_id))
    return {"deleted": True}


async def owned_note(session: Any, owner_id: str, agent_id: str, note_id: str) -> SemanticMemoryRow:
    await owned_agent(session, owner_id, agent_id)
    row = await session.get(SemanticMemoryRow, note_id)
    if row is None or row.owner_id != owner_id or row.agent_id != agent_id:
        raise LonoraError("knowledge_note_not_found", 404)
    return row
