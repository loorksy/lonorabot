"""Attributed revisions of the owner profile, owner preferences and each Agent's memory.

Every commit records the text before and after it, who made it (the owner, an Agent
or the system) and the owner message an Agent answered. The owner undoes one change as
a new, attributed commit that takes back only that change; later changes stay and
nothing is rewritten in place.
"""

import difflib
import re
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


def undo_change(before: str, after: str, current: str) -> str | None:
    """Take back one change (``before`` -> ``after``) from ``current``, keeping the rest.

    The lines the change added are removed and the lines it removed come back where
    they were; anything a later change wrote stays. None means a later change edited
    the very lines this change wrote, so undoing it would overwrite that later change.
    """
    if current == after:
        return before
    base, target, ours = after.splitlines(), before.splitlines(), current.splitlines()
    # Where each line of the changed text is now if no later change touched it, and
    # which lines a later change removed outright (rather than rewrote).
    where: dict[int, int] = {}
    removed: set[int] = set()
    later = difflib.SequenceMatcher(None, base, ours, autojunk=False).get_opcodes()
    for tag, start, stop, low, _ in later:
        for offset in range(stop - start):
            if tag == "equal":
                where[start + offset] = low + offset
            elif tag == "delete":
                removed.add(start + offset)
    edits: list[tuple[int, int, list[str]]] = []
    hunks = difflib.SequenceMatcher(None, base, target, autojunk=False).get_opcodes()
    for tag, start, stop, low, high in hunks:
        if tag == "equal":
            continue
        if start < stop:
            spots = [where.get(index) for index in range(start, stop)]
            if tag == "delete" and all(index in removed for index in range(start, stop)):
                continue  # A later change already removed what this change added.
            first = spots[0]
            if first is None or spots != list(range(first, first + len(spots))):
                return None
            begin, end = first, first + len(spots)
        elif start > 0 and start - 1 in where:
            begin = end = where[start - 1] + 1
        elif start in where:
            begin = end = where[start]
        else:
            begin = end = 0 if start == 0 else len(ours)
        # A line a later change already brought back is not added twice.
        elsewhere = {line.strip() for line in ours[:begin] + ours[end:] if line.strip()}
        restored = [line for line in target[low:high] if line.strip() not in elsewhere]
        edits.append((begin, end, restored))
    lines = list(ours)
    for begin, end, restored in reversed(edits):
        lines[begin:end] = restored
    text = re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()
    return text + "\n" if text else ""


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
