"""Attributed revisions of the owner profile, owner preferences and each Agent's memory.

Every commit records the text before and after it, who made it (the owner, an Agent
or the system) and the owner message an Agent answered. The owner reverts a change by
restoring its prior text as a new, attributed commit; nothing is rewritten in place.
"""

import difflib
from typing import Any, Literal

from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import AgentRow, MemoryRevisionRow

Document = Literal["owner_profile", "owner_preferences", "agent_memory"]
Author = Literal["owner", "agent", "system"]
# Newest revisions kept per document; older ones are pruned on commit.
REVISIONS_KEPT = 100
MAX_DIFF_LINES = 60
DIFF_LINE_CHARS = 400


async def record_revision(
    session: AsyncSession,
    owner_id: str,
    *,
    document: Document,
    agent_id: str | None,
    version: int | None,
    previous_content: str,
    content: str,
    author: Author,
    change: str,
    author_agent_id: str | None = None,
    source_message_id: str | None = None,
    source_run_id: str | None = None,
    reverted_revision_id: str | None = None,
) -> MemoryRevisionRow:
    scope = _scope(owner_id, document, agent_id)
    if version is None:
        # Preferences carry no document revision; number their changes in order.
        version = (
            int(
                await session.scalar(
                    select(func.coalesce(func.max(MemoryRevisionRow.version), 0)).where(*scope)
                )
                or 0
            )
            + 1
        )
    row = MemoryRevisionRow(
        owner_id=owner_id,
        document=document,
        agent_id=agent_id,
        version=version,
        previous_content=previous_content,
        content=content,
        author=author,
        author_agent_id=author_agent_id,
        source_message_id=source_message_id,
        source_run_id=source_run_id,
        change=change,
        reverted_revision_id=reverted_revision_id,
    )
    session.add(row)
    await session.flush()
    kept = (
        select(MemoryRevisionRow.id)
        .where(*scope)
        .order_by(MemoryRevisionRow.version.desc(), MemoryRevisionRow.created_at.desc())
        .limit(REVISIONS_KEPT)
    )
    await session.execute(
        delete(MemoryRevisionRow)
        .where(*scope, MemoryRevisionRow.id.not_in(kept))
        .execution_options(synchronize_session=False)
    )
    return row


def _scope(owner_id: str, document: str, agent_id: str | None) -> list[Any]:
    return [
        MemoryRevisionRow.owner_id == owner_id,
        MemoryRevisionRow.document == document,
        MemoryRevisionRow.agent_id.is_(None)
        if agent_id is None
        else MemoryRevisionRow.agent_id == agent_id,
    ]


async def list_revisions(
    session: AsyncSession,
    owner_id: str,
    documents: tuple[Document, ...],
    agent_id: str | None = None,
    limit: int = 20,
) -> list[MemoryRevisionRow]:
    query = select(MemoryRevisionRow).where(
        MemoryRevisionRow.owner_id == owner_id,
        MemoryRevisionRow.document.in_(documents),
        MemoryRevisionRow.agent_id.is_(None)
        if agent_id is None
        else MemoryRevisionRow.agent_id == agent_id,
    )
    return list(
        await session.scalars(
            query.order_by(
                MemoryRevisionRow.created_at.desc(), MemoryRevisionRow.version.desc()
            ).limit(max(1, min(limit, 50)))
        )
    )


def text_changes(before: str, after: str) -> tuple[list[dict[str, str]], bool]:
    """Added and removed lines in order, bounded for display."""
    changes: list[dict[str, str]] = []
    for line in difflib.ndiff(before.splitlines(), after.splitlines()):
        if line[:2] not in ("+ ", "- "):
            continue
        text = line[2:]
        if not text.strip():
            continue
        changes.append(
            {"change": "added" if line[0] == "+" else "removed", "text": text[:DIFF_LINE_CHARS]}
        )
    return changes[:MAX_DIFF_LINES], len(changes) > MAX_DIFF_LINES


async def revision_data(
    session: AsyncSession, row: MemoryRevisionRow, *, preference_changes: Any = None
) -> dict[str, Any]:
    author_name = None
    if row.author_agent_id:
        author_name = await session.scalar(
            select(AgentRow.name).where(AgentRow.id == row.author_agent_id)
        )
    if preference_changes is not None:
        changes, truncated = preference_changes(row.previous_content, row.content), False
    else:
        changes, truncated = text_changes(row.previous_content, row.content)
    return {
        "id": row.id,
        "document": row.document,
        "agent_id": row.agent_id,
        "version": row.version,
        "author": row.author,
        "author_agent_id": row.author_agent_id,
        "author_agent_name": author_name,
        "from_owner_message": row.source_message_id is not None,
        "change": row.change,
        "reverted_revision_id": row.reverted_revision_id,
        "created_at": row.created_at.isoformat(),
        "changes": changes,
        "changes_truncated": truncated,
    }
