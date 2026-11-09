"""Owner-defined chat lists (WP-B): named filters over the owner's conversations.

A name is unique per owner (``chat_list_name_taken``); members are the owner's thread ids,
replaced as a whole by ``set_members``. Every change is one ``chat_list.updated`` event;
a deleted list carries ``deleted: true``.
"""

from typing import Any

from lonora_contracts.chat_lists import ChatListCreate, ChatListMembers, ChatListUpdate
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import ChatListMemberRow, ChatListRow, ThreadRow


def list_data(row: ChatListRow, thread_ids: list[str]) -> dict[str, Any]:
    return {
        "id": row.id,
        "name": row.name,
        "position": row.position,
        "thread_ids": thread_ids,
        "created_at": row.created_at.isoformat(),
        "updated_at": row.updated_at.isoformat(),
    }


async def members_of(session: AsyncSession, list_ids: list[str]) -> dict[str, list[str]]:
    members: dict[str, list[str]] = {list_id: [] for list_id in list_ids}
    if list_ids:
        rows = await session.execute(
            select(ChatListMemberRow.list_id, ChatListMemberRow.thread_id)
            .where(ChatListMemberRow.list_id.in_(list_ids))
            .order_by(ChatListMemberRow.thread_id)
        )
        for list_id, thread_id in rows:
            members[list_id].append(thread_id)
    return members


async def owned_list(
    session: AsyncSession, owner_id: str, list_id: str, lock: bool = False
) -> ChatListRow:
    query = select(ChatListRow).where(ChatListRow.id == list_id, ChatListRow.owner_id == owner_id)
    if lock:
        query = query.with_for_update()
    row = await session.scalar(query)
    if row is None:
        raise LonoraError("chat_list_not_found", 404)
    return row


async def list_chat_lists(session: AsyncSession, owner_id: str) -> list[dict[str, Any]]:
    rows = list(
        await session.scalars(
            select(ChatListRow)
            .where(ChatListRow.owner_id == owner_id)
            .order_by(ChatListRow.position, ChatListRow.created_at, ChatListRow.id)
        )
    )
    members = await members_of(session, [row.id for row in rows])
    return [list_data(row, members[row.id]) for row in rows]


async def name_available(
    session: AsyncSession, owner_id: str, name: str, *, except_id: str | None = None
) -> None:
    query = select(ChatListRow.id).where(
        ChatListRow.owner_id == owner_id, func.lower(ChatListRow.name) == name.lower()
    )
    if except_id:
        query = query.where(ChatListRow.id != except_id)
    if await session.scalar(query) is not None:
        raise LonoraError("chat_list_name_taken", 409)


async def create_chat_list(
    session: AsyncSession, owner_id: str, body: ChatListCreate
) -> dict[str, Any]:
    await name_available(session, owner_id, body.name)
    position = await session.scalar(
        select(func.coalesce(func.max(ChatListRow.position), -1)).where(
            ChatListRow.owner_id == owner_id
        )
    )
    row = ChatListRow(owner_id=owner_id, name=body.name, position=int(position or 0) + 1)
    session.add(row)
    await session.flush()
    emit(session, owner_id, "chat_list.updated", payload={"id": row.id})
    return list_data(row, [])


async def update_chat_list(
    session: AsyncSession, owner_id: str, list_id: str, body: ChatListUpdate
) -> dict[str, Any]:
    row = await owned_list(session, owner_id, list_id, lock=True)
    if body.name is not None and body.name != row.name:
        await name_available(session, owner_id, body.name, except_id=row.id)
        row.name = body.name
    if body.position is not None:
        row.position = body.position
    row.updated_at = utcnow()
    emit(session, owner_id, "chat_list.updated", payload={"id": row.id})
    return list_data(row, (await members_of(session, [row.id]))[row.id])


async def delete_chat_list(session: AsyncSession, owner_id: str, list_id: str) -> None:
    row = await owned_list(session, owner_id, list_id, lock=True)
    emit(session, owner_id, "chat_list.updated", payload={"id": row.id, "deleted": True})
    await session.delete(row)


async def set_members(
    session: AsyncSession, owner_id: str, list_id: str, body: ChatListMembers
) -> dict[str, Any]:
    """Replace the list's conversations; every id must be one of the owner's threads."""
    row = await owned_list(session, owner_id, list_id, lock=True)
    if body.thread_ids:
        owned = set(
            await session.scalars(
                select(ThreadRow.id).where(
                    ThreadRow.owner_id == owner_id, ThreadRow.id.in_(body.thread_ids)
                )
            )
        )
        if owned != set(body.thread_ids):
            raise LonoraError("thread_not_found", 404)
    await session.execute(delete(ChatListMemberRow).where(ChatListMemberRow.list_id == row.id))
    for thread_id in body.thread_ids:
        session.add(ChatListMemberRow(list_id=row.id, thread_id=thread_id))
    row.updated_at = utcnow()
    await session.flush()
    emit(session, owner_id, "chat_list.updated", payload={"id": row.id})
    return list_data(row, list(body.thread_ids))
