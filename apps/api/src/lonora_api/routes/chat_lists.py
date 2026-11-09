from typing import Any

from fastapi import APIRouter, Depends, Request
from lonora_auth.identity import OwnerIdentity
from lonora_contracts.chat_lists import ChatListCreate, ChatListMembers, ChatListUpdate
from lonora_db.chat_lists import (
    create_chat_list,
    delete_chat_list,
    list_chat_lists,
    set_members,
    update_chat_list,
)

from ..middleware.auth import require_owner, runtime

router = APIRouter(prefix="/chat-lists")


@router.get("")
async def read_lists(
    request: Request, owner: OwnerIdentity = Depends(require_owner)
) -> list[dict[str, Any]]:
    async with runtime(request).db.sessions() as session:
        return await list_chat_lists(session, owner.id)


@router.post("", status_code=201)
async def create(
    request: Request, body: ChatListCreate, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return await create_chat_list(session, owner.id, body)


@router.put("/{list_id}")
async def update(
    request: Request,
    list_id: str,
    body: ChatListUpdate,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return await update_chat_list(session, owner.id, list_id, body)


@router.delete("/{list_id}")
async def delete(
    request: Request, list_id: str, owner: OwnerIdentity = Depends(require_owner)
) -> dict[str, bool]:
    async with runtime(request).db.sessions() as session, session.begin():
        await delete_chat_list(session, owner.id, list_id)
    return {"deleted": True}


@router.put("/{list_id}/members")
async def members(
    request: Request,
    list_id: str,
    body: ChatListMembers,
    owner: OwnerIdentity = Depends(require_owner),
) -> dict[str, Any]:
    async with runtime(request).db.sessions() as session, session.begin():
        return await set_members(session, owner.id, list_id, body)
