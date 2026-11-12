from typing import Any

from lonora_contracts.domain import ThreadCreate, ThreadOptions
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .schema import AgentRow, GroupRow, RunRow, ThreadRow
from .transactions import owned_agent, owned_thread


def thread_options(row: ThreadRow) -> ThreadOptions:
    """The chat's options with their defaults; unknown stored keys are ignored."""
    stored = row.options or {}
    return ThreadOptions(web_search=stored.get("web_search") is True)


def thread_data(row: ThreadRow) -> dict[str, Any]:
    return {
        "id": row.id,
        "agent_id": row.agent_id,
        "group_id": row.group_id,
        "title": row.title,
        "options": thread_options(row).model_dump(),
        "created_at": row.created_at.isoformat(),
    }


async def set_thread_options(
    session: AsyncSession, owner_id: str, thread_id: str, options: ThreadOptions
) -> ThreadRow:
    """Per-chat options (Q33); the agent reads them when it builds its next turn."""
    row = await owned_thread(session, owner_id, thread_id, lock=True)
    row.options = {**(row.options or {}), **options.model_dump()}
    emit(
        session,
        owner_id,
        "thread.updated",
        thread_id=row.id,
        agent_id=row.agent_id,
        payload={"thread_id": row.id, "options": thread_options(row).model_dump()},
    )
    return row


async def create_thread(
    session: AsyncSession, owner_id: str, request: ThreadCreate, *, purpose: str = "conversation"
) -> ThreadRow:
    if purpose not in {"conversation", "work"}:
        raise LonoraError("thread_purpose_invalid", 422)
    if bool(request.agent_id) == bool(request.group_id):
        raise LonoraError("thread_target_required")
    if request.agent_id:
        await owned_agent(session, owner_id, request.agent_id)
    if request.group_id:
        group = await session.get(GroupRow, request.group_id)
        if group is None or group.owner_id != owner_id:
            raise LonoraError("group_not_found", 404)
    row = ThreadRow(owner_id=owner_id, purpose=purpose, **request.model_dump())
    session.add(row)
    await session.flush()
    return row


async def conversation_thread(session: AsyncSession, owner_id: str, agent_id: str) -> ThreadRow:
    """One atomic canonical direct conversation shared by owner messages and peer requests."""
    # Serialize canonical creation without blocking FK KEY SHARE on messages/runs.
    # FOR UPDATE here would invert agent/thread locks with an owner send or reverse peer.
    agent = await session.scalar(
        select(AgentRow)
        .where(AgentRow.id == agent_id, AgentRow.owner_id == owner_id)
        .with_for_update(key_share=True)
    )
    if agent is None:
        raise LonoraError("agent_not_found", 404)
    row = await session.scalar(
        select(ThreadRow)
        .where(
            ThreadRow.owner_id == owner_id,
            ThreadRow.agent_id == agent_id,
            ThreadRow.group_id.is_(None),
            ThreadRow.purpose == "conversation",
        )
        .order_by(ThreadRow.created_at, ThreadRow.id)
        .limit(1)
    )
    return (
        row
        if row is not None
        else await create_thread(session, owner_id, ThreadCreate(agent_id=agent_id, title=""))
    )


async def list_threads(
    session: AsyncSession, owner_id: str, agent_id: str | None = None
) -> list[ThreadRow]:
    query = select(ThreadRow).where(
        ThreadRow.owner_id == owner_id, ThreadRow.purpose == "conversation"
    )
    if agent_id:
        query = query.where(ThreadRow.agent_id == agent_id)
    return list(
        (await session.scalars(query.order_by(ThreadRow.created_at.desc()).limit(200))).all()
    )


async def report_thread(session: AsyncSession, run: RunRow) -> str:
    """Where a Run's owner-facing records belong.

    A wake works in its own work lane but reports to the conversation it came
    from, when that is the same Agent's direct conversation. Anything else keeps
    the Run's own thread.
    """
    origin_id = run.model_metadata.get("origin_thread_id")
    if not isinstance(origin_id, str) or not origin_id or origin_id == run.thread_id:
        return run.thread_id
    source = await session.get(ThreadRow, run.thread_id)
    origin = await session.get(ThreadRow, origin_id)
    if (
        source is not None
        and origin is not None
        and source.purpose == "work"
        and origin.purpose == "conversation"
        and origin.group_id is None
        and origin.owner_id == source.owner_id
        and origin.agent_id == source.agent_id == run.agent_id
    ):
        return origin.id
    return run.thread_id


async def origin_read_threads(session: AsyncSession, run: RunRow) -> list[str]:
    """Threads a Run may read: its own, plus the conversation it came from.

    A wake, Task or opportunity Run works in its own work lane but still reads the
    conversation it came from (the Agent's own, or a group it belongs to).
    """
    origin_id = run.model_metadata.get("origin_thread_id")
    if not isinstance(origin_id, str) or not origin_id or origin_id == run.thread_id:
        return [run.thread_id]
    source = await session.get(ThreadRow, run.thread_id)
    origin = await session.get(ThreadRow, origin_id)
    if (
        source is not None
        and source.purpose == "work"
        and origin is not None
        and origin.purpose == "conversation"
        and origin.owner_id == source.owner_id
        and source.agent_id == run.agent_id
    ):
        if origin.agent_id == run.agent_id:
            return [run.thread_id, origin.id]
        if origin.group_id:
            group = await session.get(GroupRow, origin.group_id)
            if (
                group
                and group.owner_id == origin.owner_id
                and run.agent_id in group.payload.get("member_ids", [])
            ):
                return [run.thread_id, origin.id]
    return [run.thread_id]
