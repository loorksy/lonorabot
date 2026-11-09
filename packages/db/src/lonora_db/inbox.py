"""Bounded inbox projection: canonical conversations, the owner's state of each and the
latest message the owner can see (WP-A)."""

from typing import Any, cast

from lonora_core.message_preview import attachment_kind, message_kind, message_preview
from sqlalchemy import Text, func, or_, select
from sqlalchemy import cast as sql_cast
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import ArtifactRow, MessageRow, RunRow, ThreadPrefsRow, ThreadRow
from .thread_prefs import STARTED_STATUSES, consumed, steered_message_ids


async def inbox_projection(session: AsyncSession, owner_id: str) -> list[dict[str, Any]]:
    prefs = select(ThreadPrefsRow).where(ThreadPrefsRow.owner_id == owner_id).subquery()
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
    # The latest message the owner can see: after the «مسح» cursor, and carrying text, a
    # rich answer or an attachment.
    messages = (
        select(
            MessageRow.id.label("message_id"),
            MessageRow.thread_id,
            MessageRow.role,
            MessageRow.agent_id.label("message_agent_id"),
            MessageRow.content,
            MessageRow.rich_content,
            MessageRow.attachment_ids,
            MessageRow.seq,
            MessageRow.created_at.label("message_at"),
            func.row_number()
            .over(partition_by=MessageRow.thread_id, order_by=MessageRow.seq.desc())
            .label("message_rank"),
        )
        .join(ThreadRow, ThreadRow.id == MessageRow.thread_id)
        .outerjoin(prefs, prefs.c.thread_id == MessageRow.thread_id)
        .where(
            ThreadRow.owner_id == owner_id,
            MessageRow.role.in_(["user", "assistant"]),
            MessageRow.seq > func.coalesce(prefs.c.hidden_before_seq, 0),
            or_(
                MessageRow.content != "",
                MessageRow.rich_content.is_not(None),
                sql_cast(MessageRow.attachment_ids, Text).not_in(["[]", "null"]),
            ),
        )
        .subquery()
    )
    # Unread: the agent's messages after the read cursor (the cursor never sits before
    # the «مسح» cursor, so hidden messages are never unread).
    unread = (
        select(MessageRow.thread_id, func.count().label("unread_count"))
        .join(ThreadRow, ThreadRow.id == MessageRow.thread_id)
        .outerjoin(prefs, prefs.c.thread_id == MessageRow.thread_id)
        .where(
            ThreadRow.owner_id == owner_id,
            MessageRow.role == "assistant",
            MessageRow.seq > func.coalesce(prefs.c.last_read_seq, 0),
        )
        .group_by(MessageRow.thread_id)
        .subquery()
    )
    started = (
        select(RunRow.thread_id, func.max(RunRow.input_seq).label("started_seq"))
        .join(ThreadRow, ThreadRow.id == RunRow.thread_id)
        .where(ThreadRow.owner_id == owner_id, RunRow.status.in_(STARTED_STATUSES))
        .group_by(RunRow.thread_id)
        .subquery()
    )
    # One query, no per-agent request/query fanout. Exclude secondary work/history threads.
    query = (
        select(
            threads.c.thread_id,
            threads.c.agent_id,
            threads.c.group_id,
            threads.c.created_at,
            messages.c.message_id,
            messages.c.role,
            messages.c.message_agent_id,
            messages.c.content,
            messages.c.rich_content,
            messages.c.attachment_ids,
            messages.c.seq,
            messages.c.message_at,
            prefs.c.last_read_seq,
            prefs.c.marked_unread,
            prefs.c.muted,
            prefs.c.archived,
            prefs.c.favourite,
            prefs.c.pinned_order,
            prefs.c.hidden_before_seq,
            unread.c.unread_count,
            started.c.started_seq,
        )
        .outerjoin(
            messages,
            (messages.c.thread_id == threads.c.thread_id) & (messages.c.message_rank == 1),
        )
        .outerjoin(prefs, prefs.c.thread_id == threads.c.thread_id)
        .outerjoin(unread, unread.c.thread_id == threads.c.thread_id)
        .outerjoin(started, started.c.thread_id == threads.c.thread_id)
        .where(threads.c.canonical_rank == 1)
        .order_by(
            func.coalesce(messages.c.message_at, threads.c.created_at).desc(),
            threads.c.thread_id,
        )
        .limit(200)
    )
    rows = list((await session.execute(query)).mappings())
    attachment_ids = [
        str(identifier)
        for row in rows
        for identifier in cast(list[Any], row["attachment_ids"] or [])
    ]
    artifacts: dict[str, dict[str, Any]] = {}
    if attachment_ids:
        for artifact_id, payload in await session.execute(
            select(ArtifactRow.id, ArtifactRow.payload).where(
                ArtifactRow.id.in_(list(dict.fromkeys(attachment_ids)))
            )
        ):
            artifacts[artifact_id] = payload
    steered = await steered_message_ids(
        session, [row["message_id"] for row in rows if row["role"] == "user"]
    )
    result: list[dict[str, Any]] = []
    for row in rows:
        at = row["message_at"] or row["created_at"]
        message = None
        if row["message_id"] is not None:
            attached = [
                artifacts[identifier]
                for identifier in cast(list[Any], row["attachment_ids"] or [])
                if identifier in artifacts
            ]
            kinds = [attachment_kind(str(item.get("media_type", ""))) for item in attached]
            rich = row["rich_content"]
            message = {
                "id": row["message_id"],
                "role": row["role"],
                "agent_id": row["message_agent_id"],
                "content": row["content"][:500],
                "created_at": row["message_at"].isoformat(),
                "seq": row["seq"],
                "kind": message_kind(rich, kinds),
                "preview": message_preview(
                    row["content"], rich, [str(item.get("name", "")) for item in attached]
                ),
                "attachments": {"count": len(attached), "kinds": kinds},
            }
            message["consumed"] = consumed(message, int(row["started_seq"] or 0), steered)
        result.append(
            {
                "thread_id": row["thread_id"],
                "agent_id": row["agent_id"],
                "group_id": row["group_id"],
                "last_message": message,
                "last_activity_at": at.isoformat(),
                "unread_count": int(row["unread_count"] or 0),
                "last_read_seq": int(row["last_read_seq"] or 0),
                "marked_unread": bool(row["marked_unread"]),
                "muted": bool(row["muted"]),
                "archived": bool(row["archived"]),
                "favourite": bool(row["favourite"]),
                "pinned_order": row["pinned_order"],
                "hidden_before_seq": int(row["hidden_before_seq"] or 0),
            }
        )
    return result
