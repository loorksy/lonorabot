from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import ThreadCreate, ThreadOptions
from lonora_contracts.thread_prefs import (
    ReadCursor,
    ThreadPrefsBulkUpdate,
    ThreadPrefsUpdate,
    ThreadSettings,
)
from lonora_db.authority_lock import authority_lock
from lonora_db.inbox import inbox_projection
from lonora_db.obligations import prepare_delete
from lonora_db.thread_prefs import (
    clear_history,
    mark_read,
    read_all,
    set_thread_settings,
    thread_settings,
    update_prefs,
    update_prefs_bulk,
)
from lonora_db.threads import create_thread, list_threads, set_thread_options, thread_data
from lonora_db.transactions import owned_thread

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/threads")

# Fixed paths first: FastAPI matches routes in declaration order.


@router.get("/inbox")
async def inbox(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        return await inbox_projection(session, owner.id)


@router.post("/read-all")
async def read_every_thread(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session, session.begin():
        return await read_all(session, owner.id)


@router.post("/prefs")
async def update_many_prefs(
    request: Request, body: ThreadPrefsBulkUpdate, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session, session.begin():
        return await update_prefs_bulk(session, owner.id, body)


@router.get("/settings")
async def read_settings(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session:
        return (await thread_settings(session, owner.id)).model_dump()


@router.put("/settings")
async def write_settings(
    request: Request, body: ThreadSettings, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return (await set_thread_settings(session, owner.id, body)).model_dump()


@router.get("")
async def threads(
    request: Request, agent_id: str | None = None, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        return [thread_data(row) for row in await list_threads(session, owner.id, agent_id)]


@router.post("", status_code=201)
async def create(
    request: Request, body: ThreadCreate, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return thread_data(await create_thread(session, owner.id, body))


@router.get("/{thread_id}")
async def thread(
    request: Request, thread_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session:
        return thread_data(await owned_thread(session, owner.id, thread_id))


@router.delete("/{thread_id}")
async def delete(
    request: Request, thread_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    async with runtime(request).db.sessions() as session, session.begin():
        candidate = await owned_thread(session, owner.id, thread_id)
        if candidate.agent_id:
            # Grants signed here are revoked: take the agent's authority lock before the
            # thread lock, in the same order as deleting the agent.
            await authority_lock(session, candidate.agent_id)
        thread = await owned_thread(session, owner.id, thread_id, lock=True)
        # Refused while a trade from this conversation is uncertain; otherwise its
        # grants and Super Bot requests are settled, and the records survive.
        await prepare_delete(session, owner.id, thread_id=thread_id)
        await session.delete(thread)
    return {"deleted": True}


@router.put("/{thread_id}/options")
async def options(
    request: Request,
    thread_id: str,
    body: ThreadOptions,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    """Per-chat options (Q33): ``web_search`` makes the agent gather sources first."""
    async with runtime(request).db.sessions() as session, session.begin():
        return thread_data(await set_thread_options(session, owner.id, thread_id, body))


@router.post("/{thread_id}/read")
async def read(
    request: Request,
    thread_id: str,
    body: ReadCursor,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return await mark_read(session, owner.id, thread_id, body.seq)


@router.patch("/{thread_id}/prefs")
async def prefs(
    request: Request,
    thread_id: str,
    body: ThreadPrefsUpdate,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return await update_prefs(session, owner.id, thread_id, body)


@router.post("/{thread_id}/clear")
async def clear(
    request: Request, thread_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    """«مسح»: hide the history for the owner; the thread, grants, journal and agent stay."""
    async with runtime(request).db.sessions() as session, session.begin():
        return await clear_history(session, owner.id, thread_id)
