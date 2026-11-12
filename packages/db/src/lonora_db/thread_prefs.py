"""The owner's per-conversation state (WP-A), shared by web and mobile.

One ``ln_thread_prefs`` row per conversation holds the read cursor (max-wins, clamped to
the latest message), marked-unread, mute, archive, favourite, the pin order (1..3 per
owner, newest on top; a fourth pin is refused with ``thread_pin_limit``; archiving unpins
and pinning unarchives) and the «مسح» cursor ``hidden_before_seq``: messages at or before
it are hidden from the owner's history, inbox and search while the thread, its grants,
the journal and the agent stay. Every change is a ``thread.read`` or
``thread.prefs_updated`` event.

``keep_archived`` («إبقاء المحادثات مؤرشفة») is one owner setting; when it is off,
``unarchive_on_message`` returns an archived conversation to the list on a new message.
The gateway applies it to every ``message.created`` event (``thread_prefs_tick``), so
every path that writes a message is covered.

«Consumed» (two accent ticks) is derived, never stored: an owner message is consumed
once a run of its conversation has started with ``input_seq`` at or past it, or once the
message was steered into a running run and merged.
"""

from typing import Any

from lonora_contracts.domain import utcnow
from lonora_contracts.thread_prefs import ThreadPrefsBulkUpdate, ThreadPrefsUpdate, ThreadSettings
from lonora_core.user_error import LonoraError
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from .events import PUBLIC_CURSOR, emit, public_cursor_expression
from .owner_signals import record_signal
from .schema import EventRow, RunRow, SettingRow, SteeringRow, ThreadPrefsRow, ThreadRow
from .transactions import SettingsRepository, owned_thread

PIN_LIMIT = 3
# A run in these states has read the conversation up to its input_seq.
STARTED_STATUSES = ("running", "waiting_input", "waiting_takeover", "completed", "failed")


def prefs_data(row: ThreadPrefsRow | None, thread_id: str) -> dict[str, Any]:
    if row is None:
        return {
            "thread_id": thread_id,
            "last_read_seq": 0,
            "marked_unread": False,
            "muted": False,
            "archived": False,
            "favourite": False,
            "pinned_order": None,
            "hidden_before_seq": 0,
            "updated_at": None,
        }
    return {
        "thread_id": row.thread_id,
        "last_read_seq": row.last_read_seq,
        "marked_unread": row.marked_unread,
        "muted": row.muted,
        "archived": row.archived,
        "favourite": row.favourite,
        "pinned_order": row.pinned_order,
        "hidden_before_seq": row.hidden_before_seq,
        "updated_at": row.updated_at.isoformat(),
    }


async def lock_prefs(session: AsyncSession, owner_id: str) -> None:
    """Serialize the owner's preference writes, so the pin limit and orders hold."""
    if session.get_bind().dialect.name == "postgresql":
        await session.execute(
            text("SELECT pg_advisory_xact_lock(hashtextextended(:key, 0))"),
            {"key": "thread-prefs:" + owner_id},
        )


async def prefs_row(session: AsyncSession, owner_id: str, thread_id: str) -> ThreadPrefsRow:
    """The owner's row for the thread, created when missing."""
    await owned_thread(session, owner_id, thread_id)
    row = await session.get(ThreadPrefsRow, {"owner_id": owner_id, "thread_id": thread_id})
    if row is None:
        row = ThreadPrefsRow(owner_id=owner_id, thread_id=thread_id)
        session.add(row)
        await session.flush()
    return row


async def hidden_floor(session: AsyncSession, owner_id: str, thread_id: str) -> int:
    """The seq at or before which the owner's history is hidden (0: nothing hidden)."""
    row = await session.get(ThreadPrefsRow, {"owner_id": owner_id, "thread_id": thread_id})
    return row.hidden_before_seq if row else 0


def latest_seq(thread: ThreadRow) -> int:
    return thread.next_seq - 1


async def mark_read(
    session: AsyncSession, owner_id: str, thread_id: str, seq: int
) -> dict[str, Any]:
    """Max-wins read cursor, clamped to the latest message; clears marked-unread."""
    await lock_prefs(session, owner_id)
    thread = await owned_thread(session, owner_id, thread_id)
    row = await prefs_row(session, owner_id, thread_id)
    target = min(max(seq, row.last_read_seq), latest_seq(thread))
    if target != row.last_read_seq or row.marked_unread:
        row.last_read_seq = target
        row.marked_unread = False
        row.updated_at = utcnow()
        emit(
            session,
            owner_id,
            "thread.read",
            thread_id=thread_id,
            payload={"thread_id": thread_id, "last_read_seq": row.last_read_seq},
        )
        # When the owner reads is part of the owner model (8.1).
        record_signal(
            session, owner_id, "thread_read", thread_id=thread_id, agent_id=thread.agent_id
        )
    return prefs_data(row, thread_id)


async def read_all(session: AsyncSession, owner_id: str) -> list[dict[str, Any]]:
    """Every conversation read up to its latest message; one event per changed thread."""
    await lock_prefs(session, owner_id)
    threads = await session.scalars(
        select(ThreadRow)
        .where(ThreadRow.owner_id == owner_id, ThreadRow.purpose == "conversation")
        .order_by(ThreadRow.created_at, ThreadRow.id)
    )
    result: list[dict[str, Any]] = []
    for thread in threads:
        row = await prefs_row(session, owner_id, thread.id)
        if row.last_read_seq < latest_seq(thread) or row.marked_unread:
            row.last_read_seq = max(row.last_read_seq, latest_seq(thread))
            row.marked_unread = False
            row.updated_at = utcnow()
            emit(
                session,
                owner_id,
                "thread.read",
                thread_id=thread.id,
                payload={"thread_id": thread.id, "last_read_seq": row.last_read_seq},
            )
            result.append(prefs_data(row, thread.id))
    if result:
        # One tap is one read, however many conversations it marks.
        record_signal(session, owner_id, "thread_read", details={"threads": len(result)})
    return result


async def pinned_rows(session: AsyncSession, owner_id: str) -> list[ThreadPrefsRow]:
    return list(
        await session.scalars(
            select(ThreadPrefsRow)
            .where(ThreadPrefsRow.owner_id == owner_id, ThreadPrefsRow.pinned_order.is_not(None))
            .order_by(ThreadPrefsRow.pinned_order)
        )
    )


async def unpin(session: AsyncSession, owner_id: str, row: ThreadPrefsRow) -> None:
    order = row.pinned_order
    row.pinned_order = None
    if order is None:
        return
    for other in await pinned_rows(session, owner_id):
        if other.pinned_order is not None and other.pinned_order > order:
            other.pinned_order -= 1
            other.updated_at = utcnow()


async def apply_prefs(
    session: AsyncSession, owner_id: str, thread_id: str, change: ThreadPrefsUpdate
) -> ThreadPrefsRow:
    row = await prefs_row(session, owner_id, thread_id)
    if change.muted is not None:
        row.muted = change.muted
    if change.favourite is not None:
        row.favourite = change.favourite
    if change.marked_unread is not None:
        row.marked_unread = change.marked_unread
    if change.archived is not None:
        row.archived = change.archived
        if change.archived:
            # An archived conversation leaves the list, so it cannot stay pinned on top.
            await unpin(session, owner_id, row)
    if change.pinned is not None:
        if change.pinned and row.pinned_order is None:
            pinned = await pinned_rows(session, owner_id)
            if len(pinned) >= PIN_LIMIT:
                raise LonoraError("thread_pin_limit", 409)
            for other in pinned:
                if other.pinned_order is not None:
                    other.pinned_order += 1
                    other.updated_at = utcnow()
            # New pins go on top; a pinned conversation is in the list.
            row.pinned_order = 1
            row.archived = False
        elif not change.pinned:
            await unpin(session, owner_id, row)
    row.updated_at = utcnow()
    emit(
        session,
        owner_id,
        "thread.prefs_updated",
        thread_id=thread_id,
        payload=prefs_data(row, thread_id),
    )
    return row


async def update_prefs(
    session: AsyncSession, owner_id: str, thread_id: str, change: ThreadPrefsUpdate
) -> dict[str, Any]:
    await lock_prefs(session, owner_id)
    return prefs_data(await apply_prefs(session, owner_id, thread_id, change), thread_id)


async def update_prefs_bulk(
    session: AsyncSession, owner_id: str, change: ThreadPrefsBulkUpdate
) -> list[dict[str, Any]]:
    """The same change for every thread, all or nothing (a fourth pin refuses the batch)."""
    await lock_prefs(session, owner_id)
    single = ThreadPrefsUpdate.model_validate(
        change.model_dump(exclude={"thread_ids"}, exclude_unset=True)
    )
    return [
        prefs_data(await apply_prefs(session, owner_id, thread_id, single), thread_id)
        for thread_id in dict.fromkeys(change.thread_ids)
    ]


async def clear_history(session: AsyncSession, owner_id: str, thread_id: str) -> dict[str, Any]:
    """«مسح»: hide everything up to the latest message for the owner. The thread, its
    grants, the journal and the agent stay; nothing is deleted."""
    await lock_prefs(session, owner_id)
    thread = await owned_thread(session, owner_id, thread_id)
    row = await prefs_row(session, owner_id, thread_id)
    row.hidden_before_seq = max(row.hidden_before_seq, latest_seq(thread))
    # Nothing hidden can be unread.
    row.last_read_seq = max(row.last_read_seq, row.hidden_before_seq)
    row.marked_unread = False
    row.updated_at = utcnow()
    emit(
        session,
        owner_id,
        "thread.prefs_updated",
        thread_id=thread_id,
        payload=prefs_data(row, thread_id),
    )
    return prefs_data(row, thread_id)


def settings_key(owner_id: str) -> str:
    return "thread-settings:" + owner_id


async def thread_settings(session: AsyncSession, owner_id: str) -> ThreadSettings:
    return ThreadSettings.model_validate(
        await SettingsRepository().get(session, settings_key(owner_id))
    )


async def set_thread_settings(
    session: AsyncSession, owner_id: str, settings: ThreadSettings
) -> ThreadSettings:
    await SettingsRepository().put(session, settings_key(owner_id), settings.model_dump())
    return settings


async def unarchive_on_message(session: AsyncSession, owner_id: str, thread_id: str) -> bool:
    """A new message returns an archived conversation to the list unless the owner keeps
    conversations archived. True when the row changed."""
    row = await session.get(
        ThreadPrefsRow, {"owner_id": owner_id, "thread_id": thread_id}, with_for_update=True
    )
    if row is None or not row.archived:
        return False
    if (await thread_settings(session, owner_id)).keep_archived:
        return False
    row.archived = False
    row.updated_at = utcnow()
    emit(
        session,
        owner_id,
        "thread.prefs_updated",
        thread_id=thread_id,
        payload=prefs_data(row, thread_id),
    )
    return True


def cursor_key(owner_id: str) -> str:
    return "thread-prefs-cursor:" + owner_id


async def apply_message_events(session: AsyncSession, owner_id: str, limit: int = 200) -> int:
    """Apply the keep-archived rule to the ``message.created`` events published since the
    last call. A first call starts at the present: nothing was archived before the rule
    existed. Returns the number of events read."""
    public = public_cursor_expression()
    counter = await session.get(SettingRow, cursor_key(owner_id), with_for_update=True)
    if counter is None:
        current = int(
            (await session.scalar(select(func.max(public)).where(EventRow.owner_id == owner_id)))
            or 0
        )
        session.add(SettingRow(key=cursor_key(owner_id), payload={"cursor": current}))
        return 0
    cursor = int(counter.payload.get("cursor", 0))
    events = list(
        await session.scalars(
            select(EventRow)
            .where(
                EventRow.owner_id == owner_id,
                EventRow.kind == "message.created",
                public > cursor,
            )
            .order_by(public)
            .limit(limit)
        )
    )
    for event in events:
        if event.thread_id:
            await unarchive_on_message(session, owner_id, event.thread_id)
        cursor = int(event.payload[PUBLIC_CURSOR])
    if events:
        counter.payload = {"cursor": cursor}
    return len(events)


async def consumed_seq(session: AsyncSession, thread_id: str) -> int:
    """The highest owner message seq a started run of this thread has read."""
    return int(
        await session.scalar(
            select(func.max(RunRow.input_seq)).where(
                RunRow.thread_id == thread_id, RunRow.status.in_(STARTED_STATUSES)
            )
        )
        or 0
    )


async def steered_message_ids(session: AsyncSession, message_ids: list[str]) -> set[str]:
    """Owner messages merged into a running run while it worked."""
    if not message_ids:
        return set()
    return set(
        await session.scalars(
            select(SteeringRow.message_id).where(
                SteeringRow.message_id.in_(message_ids), SteeringRow.consumed.is_(True)
            )
        )
    )


def consumed(message: dict[str, Any], started_seq: int, steered: set[str]) -> bool | None:
    """Two accent ticks: the agent's run started on this owner message. None for other roles."""
    if message["role"] != "user":
        return None
    if message.get("origin") == "ui_submit":
        # Rule T: a card submission's ticks follow its own Run, not the thread's window.
        submit: dict[str, Any] = message.get("ui_submit") or {}
        return bool(submit.get("started_at"))
    return int(message["seq"]) <= started_seq or message["id"] in steered
