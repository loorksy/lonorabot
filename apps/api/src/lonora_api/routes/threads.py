from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.domain import ThreadCreate
from lonora_db.inbox import inbox_projection
from lonora_db.obligations import prepare_delete
from lonora_db.super_bot import authority_lock
from lonora_db.threads import create_thread, list_threads, thread_data
from lonora_db.transactions import owned_thread

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/threads")


@router.get("/inbox")
async def inbox(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        return await inbox_projection(session, owner.id)


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
        # grants, Super Bot requests and goals are settled, and the records survive.
        await prepare_delete(session, owner.id, thread_id=thread_id)
        await session.delete(thread)
    return {"deleted": True}
