import re
from collections.abc import Callable
from typing import Any

from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .events import emit
from .memory_revisions import record_revision
from .schema import AgentRow, EffectReceiptRow, EventRow, MemoryRow
from .transactions import owned_agent


async def read_memory(session: AsyncSession, owner_id: str, agent_id: str) -> MemoryRow:
    await owned_agent(session, owner_id, agent_id)
    row = await session.get(MemoryRow, agent_id)
    if row is None:
        raise LonoraError("memory_not_found", 404)
    return row


# The explicit view headings of an Agent's memory row; lonora_memory.profile reads the
# views. A ``# USER.md`` section from before the shared owner profile (migration 0038
# merged it there) stays in the row line for line but is no longer part of the Agent's
# view: every write keeps it, so a downgrade finds the owner's earlier preferences.
VIEW_HEADING = re.compile(r"(?m)^# (USER\.md|OPERATING\.md|(?:memory/)?MEMORY\.md)[ \t]*\n")
LEGACY_USER_VIEW = "USER.md"


def split_legacy(content: str) -> tuple[str, str]:
    """(The Agent's own view, its retired ``# USER.md`` sections with their headings)."""
    matches = list(VIEW_HEADING.finditer(content))
    if not any(match[1] == LEGACY_USER_VIEW for match in matches):
        return content, ""
    kept = [content[: matches[0].start()]]
    legacy: list[str] = []
    for position, match in enumerate(matches):
        end = matches[position + 1].start() if position + 1 < len(matches) else len(content)
        part = content[match.start() : end]
        if match[1] == LEGACY_USER_VIEW:
            legacy.append(part.strip())
        else:
            kept.append(part)
    view = re.sub(r"\n{3,}", "\n\n", "".join(kept)).strip()
    return (view + "\n" if view else ""), "\n\n".join(legacy) + "\n"


def memory_view(content: str) -> str:
    """What the Agent and the owner read and edit: the row without retired sections."""
    return split_legacy(content)[0]


def with_legacy(view: str, legacy: str) -> str:
    """The row to store: the new view, then the retired sections, unchanged."""
    if not legacy:
        return view
    head = view.rstrip("\n")
    return (head + "\n\n" if head.strip() else "") + legacy


def memory_data(row: MemoryRow) -> dict[str, Any]:
    return {
        "agent_id": row.agent_id,
        "content": memory_view(row.content),
        "version": row.version,
        "updated_at": row.updated_at.isoformat(),
    }


async def memory_provenance(session: AsyncSession, agent_id: str, version: int) -> dict[str, Any]:
    # The event index starts with owner_id. Omitting that equality made a
    # missing/legacy revision scan the entire ledger on every conversation turn.
    # Resolve ownership from the canonical Agent, never caller-supplied memory.
    owner_id = select(AgentRow.owner_id).where(AgentRow.id == agent_id).scalar_subquery()
    event = await session.scalar(
        select(EventRow)
        .where(
            EventRow.owner_id == owner_id,
            EventRow.agent_id == agent_id,
            EventRow.kind == "memory.updated",
            EventRow.payload["version"].as_integer() == version,
        )
        .order_by(EventRow.cursor.desc())
        .limit(1)
    )
    return {
        "source": event.payload.get("source", "legacy_unknown") if event else "legacy_unknown",
        "source_run_id": event.run_id if event else None,
        "event_cursor": event.cursor if event else None,
        "recorded_at": event.created_at.isoformat() if event else None,
        "authority": "untrusted_memory_content",
    }


MEMORY_CHAR_LIMIT = 30000
# Applies granular operations to the locked current content. It returns the
# new content and result details, or raises before anything is written.
MemoryTransform = Callable[[str, int], tuple[str, dict[str, Any]]]


def memory_summary(row: MemoryRow) -> dict[str, Any]:
    """Revision metadata without echoing the whole document back to the model."""
    return {
        "agent_id": row.agent_id,
        "version": row.version,
        "updated_at": row.updated_at.isoformat(),
        "chars": len(memory_view(row.content)),
        "limit": MEMORY_CHAR_LIMIT,
    }


# Checks a whole-document write against the locked current text before it is saved.
MemoryValidator = Callable[[str, str], None]


async def commit_memory(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    content: str,
    expected_version: int | None,
    effect_key: str | None = None,
    source_run_id: str | None = None,
    *,
    transform: MemoryTransform | None = None,
    validate: MemoryValidator | None = None,
    source_message_id: str | None = None,
    change: str | None = None,
    reverted_revision_id: str | None = None,
) -> dict[str, Any]:
    """One attributed revision: an Agent's own write when ``source_run_id`` is set,
    otherwise the owner's. The prior text is kept so the owner can revert it.

    ``expected_version`` None applies to the revision found under the lock (content-
    addressed operations, a revert). ``content``, the transform and the validator all
    see the Agent's view; retired sections of the row are kept as they are.
    """
    await owned_agent(session, owner_id, agent_id, lock=True)
    if effect_key:
        receipt = await session.get(EffectReceiptRow, effect_key)
        if receipt:
            return receipt.result
    # populate_existing: a row read earlier in this session must not hide a newer commit.
    row = await session.get(MemoryRow, agent_id, with_for_update=True, populate_existing=True)
    if row is None:
        raise LonoraError("memory_not_found", 404)
    if expected_version is not None and row.version != expected_version:
        raise LonoraError("version_conflict", 409)
    previous, legacy = split_legacy(row.content)
    details: dict[str, Any] = {}
    if transform is not None:
        content, details = transform(previous, row.version)
        if content == previous:
            # Nothing changed (a duplicate add, an identical patch): keep the
            # revision, emit no memory.updated, and say so instead of claiming a save.
            result = {**memory_summary(row), "changed": False, **details}
            if effect_key:
                session.add(EffectReceiptRow(key=effect_key, result=result))
            return result
    elif validate is not None:
        validate(previous, content)
    if len(content) > MEMORY_CHAR_LIMIT:
        raise LonoraError("memory_too_large", 413)
    row.content = with_legacy(content, legacy)
    row.version += 1
    row.updated_at = utcnow()
    kind = change or ("operations" if transform is not None else "document")
    await record_revision(
        session,
        owner_id,
        document="agent_memory",
        agent_id=agent_id,
        version=row.version,
        # Both sides as the owner reads them, so the history shows only this change.
        previous_content=previous,
        content=memory_view(row.content),
        author="agent" if source_run_id else "owner",
        change=kind,
        author_agent_id=agent_id if source_run_id else None,
        source_message_id=source_message_id,
        source_run_id=source_run_id,
        reverted_revision_id=reverted_revision_id,
    )
    # A whole-document write keeps returning the document it saved; granular
    # edits return the new revision and size, so nothing large travels back.
    result = (
        memory_data(row)
        if transform is None
        else {**memory_summary(row), "changed": True, **details}
    )
    if effect_key:
        session.add(EffectReceiptRow(key=effect_key, result=result))
    emit(
        session,
        owner_id,
        "memory.updated",
        agent_id=agent_id,
        run_id=source_run_id,
        payload={
            "version": row.version,
            "source": "agent_authored" if source_run_id else "owner_provided",
            "change": kind,
        },
    )
    return result
