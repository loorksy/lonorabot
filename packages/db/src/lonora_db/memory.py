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


def memory_data(row: MemoryRow) -> dict[str, Any]:
    return {
        "agent_id": row.agent_id,
        "content": row.content,
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
        "chars": len(row.content),
        "limit": MEMORY_CHAR_LIMIT,
    }


# Checks a whole-document write against the locked current text before it is saved.
MemoryValidator = Callable[[str, str], None]


async def commit_memory(
    session: AsyncSession,
    owner_id: str,
    agent_id: str,
    content: str,
    expected_version: int,
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
    otherwise the owner's. The prior text is kept so the owner can revert it."""
    await owned_agent(session, owner_id, agent_id, lock=True)
    if effect_key:
        receipt = await session.get(EffectReceiptRow, effect_key)
        if receipt:
            return receipt.result
    row = await session.get(MemoryRow, agent_id, with_for_update=True)
    if row is None:
        raise LonoraError("memory_not_found", 404)
    if row.version != expected_version:
        raise LonoraError("version_conflict", 409)
    details: dict[str, Any] = {}
    if transform is not None:
        content, details = transform(row.content, row.version)
        if content == row.content:
            # Nothing changed (a duplicate add, an identical patch): keep the
            # revision, emit no memory.updated, and say so instead of claiming a save.
            result = {**memory_summary(row), "changed": False, **details}
            if effect_key:
                session.add(EffectReceiptRow(key=effect_key, result=result))
            return result
    elif validate is not None:
        validate(row.content, content)
    if len(content) > MEMORY_CHAR_LIMIT:
        raise LonoraError("memory_too_large", 413)
    previous = row.content
    row.content = content
    row.version += 1
    row.updated_at = utcnow()
    kind = change or ("operations" if transform is not None else "document")
    await record_revision(
        session,
        owner_id,
        document="agent_memory",
        agent_id=agent_id,
        version=row.version,
        previous_content=previous,
        content=content,
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
