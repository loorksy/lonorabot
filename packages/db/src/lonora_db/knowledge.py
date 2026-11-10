"""«المعرفة» of one agent: its semantic notes and its links, as one list (Q40)."""

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .schema import KnowledgeLinkRow, SemanticMemoryRow
from .transactions import owned_agent


def note_title(payload: dict[str, Any]) -> str:
    title = str(payload.get("title") or "").strip()
    if title:
        return title
    first = str(payload.get("text", "")).strip().splitlines()
    return (first[0] if first else "")[:160]


async def knowledge_items(
    session: AsyncSession, owner_id: str, agent_id: str
) -> list[dict[str, Any]]:
    await owned_agent(session, owner_id, agent_id)
    notes = await session.scalars(
        select(SemanticMemoryRow)
        .where(SemanticMemoryRow.owner_id == owner_id, SemanticMemoryRow.agent_id == agent_id)
        .order_by(SemanticMemoryRow.updated_at.desc())
        .limit(200)
    )
    links = await session.scalars(
        select(KnowledgeLinkRow)
        .where(KnowledgeLinkRow.owner_id == owner_id, KnowledgeLinkRow.agent_id == agent_id)
        .order_by(KnowledgeLinkRow.updated_at.desc())
        .limit(200)
    )
    items = [
        {
            "id": row.id,
            "type": "note",
            "title": note_title(row.payload),
            "content": str(row.payload.get("text", "")),
            "url": None,
            "version": row.version,
            "updated_at": row.updated_at.isoformat(),
        }
        for row in notes
    ] + [
        {
            "id": row.id,
            "type": "link",
            "title": str(row.payload.get("title", "")),
            "content": str(row.payload.get("note", "")),
            "url": str(row.payload.get("url", "")),
            "version": row.version,
            "updated_at": row.updated_at.isoformat(),
        }
        for row in links
    ]
    return sorted(items, key=lambda item: item["updated_at"], reverse=True)
