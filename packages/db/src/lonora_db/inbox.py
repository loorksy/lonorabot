"""Bounded inbox projection: canonical direct threads and latest meaningful messages."""

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import MessageRow, ThreadRow


async def inbox_projection(session: AsyncSession, owner_id: str) -> list[dict[str, Any]]:
    threads = (
        select(
            ThreadRow.id.label("thread_id"),
            ThreadRow.agent_id,
            ThreadRow.group_id,
            ThreadRow.created_at,
            func.row_number()
            .over(
                partition_by=(ThreadRow.agent_id, ThreadRow.group_id),
                order_by=(ThreadRow.created_at, ThreadRow.id),
            )
            .label("canonical_rank"),
        )
        .where(ThreadRow.owner_id == owner_id, ThreadRow.purpose == "conversation")
        .subquery()
    )
    messages = (
        select(
            MessageRow.id.label("message_id"),
            MessageRow.thread_id,
            MessageRow.role,
            MessageRow.content,
            MessageRow.seq,
            MessageRow.created_at.label("message_at"),
            func.row_number()
            .over(
                partition_by=MessageRow.thread_id,
                order_by=MessageRow.seq.desc(),
            )
            .label("message_rank"),
        )
        .join(ThreadRow, ThreadRow.id == MessageRow.thread_id)
        .where(
            ThreadRow.owner_id == owner_id,
            MessageRow.role.in_(["user", "assistant"]),
            MessageRow.content != "",
        )
        .subquery()
    )
    # One query, no per-agent request/query fanout. Exclude secondary work/history threads.
    query = (
        select(threads, messages)
        .outerjoin(
            messages,
            (messages.c.thread_id == threads.c.thread_id) & (messages.c.message_rank == 1),
        )
        .where(threads.c.canonical_rank == 1)
        .order_by(
            func.coalesce(messages.c.message_at, threads.c.created_at).desc(),
            threads.c.thread_id,
        )
        .limit(200)
    )
    result: list[dict[str, Any]] = []
    for row in (await session.execute(query)).mappings():
        at = row["message_at"] or row["created_at"]
        message = (
            None
            if row["message_id"] is None
            else {
                "id": row["message_id"],
                "role": row["role"],
                "content": row["content"][:500],
                "created_at": row["message_at"].isoformat(),
                "seq": row["seq"],
            }
        )
        result.append(
            {
                "thread_id": row["thread_id"],
                "agent_id": row["agent_id"],
                "group_id": row["group_id"],
                "last_message": message,
                "last_activity_at": at.isoformat(),
            }
        )
    return result
