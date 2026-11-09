"""The owner's unified search (WP-C): chats, messages, tasks, files, knowledge, skills.

Owner-wide: it reads every owned conversation, every agent's memory and the semantic
notes. It serves the owner API only and is never exposed to an agent, whose searches
stay scoped (``lonora_tools.search``, ``session_search``). Query and text are folded the
same way (``lonora_core.search_fold``); the score is exact 6, prefix 5, contains 4, a
detail field 3; ties fall to recency. The «مسح» cursor hides messages from the owner's
search as from the history. An empty query is the browse feed: the same categories by
recency, tasks active first.
"""

import re
from typing import Any, cast

from lonora_contracts.search import SEARCH_CATEGORIES, SearchCategory
from lonora_core.search_fold import SearchColumn, fold, folded
from sqlalchemy import Select, case, func, literal, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from .memory import VIEW_HEADING, memory_view
from .schema import (
    AgentRow,
    ArtifactRow,
    GroupRow,
    MemoryRow,
    MessageRow,
    SemanticMemoryRow,
    SkillRow,
    ThreadPrefsRow,
    ThreadRow,
    TicketRow,
)

SNIPPET_CHARS = 145
ACTIVE_TASK_STATUSES = ("queued", "running", "waiting", "paused")
MARKDOWN_HEADING = re.compile(r"^#{1,6}\s+(.*?)\s*#*\s*$")
MARKDOWN_PREFIX = re.compile(r"^\s*(?:>\s*)*(?:[-*+]\s+(?:\[[ xX]\]\s+)?|\d+[.)]\s+)?")
MARKDOWN_LINK = re.compile(r"!?\[([^\]]*)\]\([^)]*\)")
MARKDOWN_MARKS = re.compile(r"(\*\*|__|\*|`+|~~)")


def escape_like(value: str) -> str:
    return value.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def snippet(text: str, query: str) -> str:
    """The reference's previewSearch: the whole text when it fits in 145 characters;
    otherwise 145 characters, starting 45 before the folded hit when the hit lies past
    the 55th character, with «…» where the text was cut."""
    text = " ".join(text.split())
    if len(text) <= SNIPPET_CHARS:
        return text
    folded_chars: list[str] = []
    origins: list[int] = []
    for index, char in enumerate(text):
        for out in fold(char) if not char.isspace() else char:
            folded_chars.append(out)
            origins.append(index)
    position = "".join(folded_chars).find(fold(query)) if query else -1
    hit = origins[position] if position >= 0 else -1
    begin = max(0, hit - 45) if hit > 55 else 0
    end = begin + SNIPPET_CHARS
    return ("…" if begin else "") + text[begin:end] + ("…" if end < len(text) else "")


def plain(markdown: str) -> str:
    """One line of readable text: list marks, quotes, emphasis and link targets removed."""
    lines = [MARKDOWN_PREFIX.sub("", line, count=1) for line in markdown.splitlines()]
    text = MARKDOWN_MARKS.sub("", MARKDOWN_LINK.sub(r"\1", " ".join(lines)))
    return " ".join(text.split())


def knowledge_sections(view: str) -> list[tuple[str, str]]:
    """A memory document as titled knowledge: (heading, plain text) per section. The
    view headings (# MEMORY.md, # OPERATING.md) name files, not knowledge: they give
    no title."""
    sections: list[tuple[str, str]] = []
    title = ""
    lines: list[str] = []

    def flush() -> None:
        text = plain("\n".join(lines))
        if text:
            sections.append((title, text))

    for line in view.splitlines():
        heading = MARKDOWN_HEADING.match(line)
        if heading is None:
            lines.append(line)
            continue
        flush()
        title = "" if VIEW_HEADING.match(line + "\n") else plain(heading[1])
        lines = []
    flush()
    return sections


class Match:
    """The SQL side of one query: the filter and the score of a primary and detail fields."""

    def __init__(self, query: str, primary: SearchColumn, *details: SearchColumn):
        self.folded_query = fold(query)
        contains = "%" + escape_like(self.folded_query) + "%"
        prefix = escape_like(self.folded_query) + "%"
        main = folded(primary)
        self.filter = or_(
            main.like(contains), *[folded(detail).like(contains) for detail in details]
        )
        self.score = case(
            (main == self.folded_query, 6),
            (main.like(prefix), 5),
            (main.like(contains), 4),
            *[(folded(detail).like(contains), 3) for detail in details],
            else_=1,
        )


def result(
    category: SearchCategory,
    identifier: str,
    title: str,
    text: str,
    query: str,
    *,
    created_at: str | None = None,
    **extra: Any,
) -> dict[str, Any]:
    return {
        "category": category,
        "id": identifier,
        "title": title,
        "snippet": snippet(text, query),
        "created_at": created_at,
        **extra,
    }


async def page(
    session: AsyncSession, query: Select[*tuple[Any, ...]], limit: int, offset: int
) -> tuple[int, list[Any]]:
    total = int(
        await session.scalar(select(func.count()).select_from(query.order_by(None).subquery())) or 0
    )
    rows = list(await session.execute(query.limit(limit).offset(offset)))
    return total, rows


async def last_activity(session: AsyncSession, owner_id: str) -> dict[str, Any]:
    """The latest message time of each agent's and group's conversation, keyed by id."""
    rows = await session.execute(
        select(ThreadRow.agent_id, ThreadRow.group_id, func.max(MessageRow.created_at))
        .join(MessageRow, MessageRow.thread_id == ThreadRow.id)
        .where(ThreadRow.owner_id == owner_id, ThreadRow.purpose == "conversation")
        .group_by(ThreadRow.agent_id, ThreadRow.group_id)
    )
    return {str(agent_id or group_id): at for agent_id, group_id, at in rows}


async def search_chats(
    session: AsyncSession, owner_id: str, q: str, limit: int, offset: int
) -> tuple[int, list[dict[str, Any]]]:
    """Agents (name; title, description, pair) and groups (name; purpose), together, by score
    then the latest message; chats with no message last (the reference's list order)."""
    if q:
        agent_match = Match(
            q,
            AgentRow.name,
            AgentRow.title,
            AgentRow.description,
            func.coalesce(AgentRow.trading_symbol, ""),
        )
        group_match = Match(
            q, GroupRow.payload["name"].as_string(), GroupRow.payload["purpose"].as_string()
        )
        agents = select(AgentRow, agent_match.score).where(
            AgentRow.owner_id == owner_id, agent_match.filter
        )
        groups = select(GroupRow, group_match.score).where(
            GroupRow.owner_id == owner_id, group_match.filter
        )
    else:
        agents = select(AgentRow, literal(0)).where(AgentRow.owner_id == owner_id)
        groups = select(GroupRow, literal(0)).where(GroupRow.owner_id == owner_id)
    activity = await last_activity(session, owner_id)
    items: list[tuple[int, float, dict[str, Any]]] = []
    for agent, score in await session.execute(agents):
        said = activity.get(agent.id)
        at = said or agent.created_at
        items.append(
            (
                int(score),
                # A chat with nothing said yet comes after every chat with a message.
                -said.timestamp() if said else float("inf"),
                result(
                    "chats",
                    agent.id,
                    agent.name,
                    # The reference's chat line: the role, then the pair it trades.
                    " · ".join(
                        part
                        for part in (agent.title or agent.description, agent.trading_symbol)
                        if part
                    ),
                    q,
                    created_at=at.isoformat(),
                    kind="agent",
                    agent_id=agent.id,
                    group_id=None,
                ),
            )
        )
    for group, score in await session.execute(groups):
        said = activity.get(group.id)
        at = said or group.created_at
        items.append(
            (
                int(score),
                -said.timestamp() if said else float("inf"),
                result(
                    "chats",
                    group.id,
                    str(group.payload.get("name", "")),
                    str(group.payload.get("purpose", "")),
                    q,
                    created_at=at.isoformat(),
                    kind="group",
                    agent_id=None,
                    group_id=group.id,
                    thread_id=group.state.get("thread_id"),
                ),
            )
        )
    items.sort(key=lambda item: (-item[0], item[1]))
    return len(items), [item[2] for item in items[offset : offset + limit]]


def visible_messages(owner_id: str) -> Select[MessageRow, str | None, str | None]:
    prefs = select(ThreadPrefsRow).where(ThreadPrefsRow.owner_id == owner_id).subquery()
    return (
        select(
            MessageRow,
            ThreadRow.agent_id.label("thread_agent_id"),
            ThreadRow.group_id.label("thread_group_id"),
        )
        .join(ThreadRow, ThreadRow.id == MessageRow.thread_id)
        .outerjoin(prefs, prefs.c.thread_id == MessageRow.thread_id)
        .where(
            ThreadRow.owner_id == owner_id,
            ThreadRow.purpose == "conversation",
            MessageRow.role.in_(["user", "assistant"]),
            MessageRow.seq > func.coalesce(prefs.c.hidden_before_seq, 0),
        )
    )


async def search_messages(
    session: AsyncSession, owner_id: str, q: str, limit: int, offset: int
) -> tuple[int, list[dict[str, Any]]]:
    query = visible_messages(owner_id)
    if q:
        match = Match(q, MessageRow.content)
        query = query.where(match.filter).order_by(match.score.desc(), MessageRow.created_at.desc())
    else:
        query = query.where(MessageRow.content != "").order_by(MessageRow.created_at.desc())
    total, rows = await page(session, query, limit, offset)
    return total, [
        result(
            "messages",
            message.id,
            "",
            message.content,
            q,
            created_at=message.created_at.isoformat(),
            thread_id=message.thread_id,
            seq=message.seq,
            role=message.role,
            agent_id=message.agent_id or thread_agent_id,
            group_id=group_id,
        )
        for message, thread_agent_id, group_id in rows
    ]


async def search_tasks(
    session: AsyncSession, owner_id: str, q: str, limit: int, offset: int
) -> tuple[int, list[dict[str, Any]]]:
    title = TicketRow.payload["title"].as_string()
    status = TicketRow.state["task"]["status"].as_string()
    query = select(TicketRow).where(
        TicketRow.owner_id == owner_id, TicketRow.state["task"].is_not(None)
    )
    if q:
        match = Match(q, title, TicketRow.payload["description"].as_string())
        query = query.where(match.filter).order_by(match.score.desc(), TicketRow.updated_at.desc())
    else:
        query = query.order_by(
            case((status.in_(ACTIVE_TASK_STATUSES), 0), else_=1), TicketRow.updated_at.desc()
        )
    total, rows = await page(session, query, limit, offset)
    return total, [
        result(
            "tasks",
            ticket.id,
            str(ticket.payload.get("title", "")),
            str(ticket.payload.get("description", "")),
            q,
            created_at=ticket.created_at.isoformat(),
            agent_id=ticket.agent_id,
            thread_id=ticket.thread_id,
            status=cast(dict[str, Any], ticket.state.get("task", {})).get("status"),
        )
        for (ticket,) in rows
    ]


async def search_files(
    session: AsyncSession, owner_id: str, q: str, limit: int, offset: int
) -> tuple[int, list[dict[str, Any]]]:
    name = ArtifactRow.payload["name"].as_string()
    query = select(ArtifactRow).where(
        ArtifactRow.owner_id == owner_id,
        or_(
            ArtifactRow.state["internal_tool_result"].as_boolean().is_(None),
            ArtifactRow.state["internal_tool_result"].as_boolean().is_(False),
        ),
    )
    if q:
        match = Match(q, name)
        query = query.where(match.filter).order_by(
            match.score.desc(), ArtifactRow.created_at.desc()
        )
    else:
        query = query.order_by(ArtifactRow.created_at.desc())
    total, rows = await page(session, query, limit, offset)
    return total, [
        result(
            "files",
            artifact.id,
            str(artifact.payload.get("name", "")),
            str(artifact.payload.get("name", "")),
            q,
            created_at=artifact.created_at.isoformat(),
            agent_id=artifact.agent_id,
            thread_id=artifact.thread_id,
            media_type=artifact.payload.get("media_type"),
            size=artifact.payload.get("size"),
        )
        for (artifact,) in rows
    ]


async def search_knowledge(
    session: AsyncSession, owner_id: str, q: str, limit: int, offset: int
) -> tuple[int, list[dict[str, Any]]]:
    """Every agent's memory document and semantic notes, labelled by agent (owner-wide)."""
    items: list[tuple[int, Any, dict[str, Any]]] = []
    memory = (
        select(MemoryRow, AgentRow.name)
        .join(AgentRow, AgentRow.id == MemoryRow.agent_id)
        .where(AgentRow.owner_id == owner_id)
    )
    notes = (
        select(SemanticMemoryRow, AgentRow.name)
        .join(AgentRow, AgentRow.id == SemanticMemoryRow.agent_id)
        .where(SemanticMemoryRow.owner_id == owner_id)
    )
    if q:
        memory = memory.where(Match(q, MemoryRow.content).filter)
        notes = notes.where(Match(q, SemanticMemoryRow.payload["text"].as_string()).filter)
    folded_query = fold(q)
    for document, agent_name in await session.execute(memory):
        # The retired owner section stays out of every view, the owner's included. A hit
        # is the first section that matches: its heading titles it (the agent's name when
        # it has none) and its plain text is the snippet; the file names never show.
        section = next(
            (
                (title, text)
                for title, text in knowledge_sections(memory_view(document.content))
                if not q or folded_query in fold(f"{title} {text}")
            ),
            None,
        )
        if section is None:
            continue
        title, text = section
        items.append(
            (
                4 if q else 0,
                document.updated_at,
                result(
                    "knowledge",
                    document.agent_id,
                    title or str(agent_name),
                    text,
                    q,
                    created_at=document.updated_at.isoformat(),
                    kind="memory",
                    agent_id=document.agent_id,
                ),
            )
        )
    for note, agent_name in await session.execute(notes):
        items.append(
            (
                4 if q else 0,
                note.updated_at,
                result(
                    "knowledge",
                    note.id,
                    str(agent_name),
                    str(note.payload.get("text", "")),
                    q,
                    created_at=note.created_at.isoformat(),
                    kind="note",
                    agent_id=note.agent_id,
                ),
            )
        )
    items.sort(key=lambda item: item[1], reverse=True)
    return len(items), [item[2] for item in items[offset : offset + limit]]


async def search_skills(
    session: AsyncSession, owner_id: str, q: str, limit: int, offset: int
) -> tuple[int, list[dict[str, Any]]]:
    name = SkillRow.payload["name"].as_string()
    query = select(SkillRow).where(SkillRow.owner_id == owner_id)
    if q:
        match = Match(
            q,
            name,
            SkillRow.payload["manifest"]["title"].as_string(),
            SkillRow.payload["manifest"]["description"].as_string(),
            SkillRow.payload["content"].as_string(),
        )
        query = query.where(match.filter).order_by(match.score.desc(), SkillRow.updated_at.desc())
    else:
        query = query.order_by(SkillRow.updated_at.desc())
    total, rows = await page(session, query, limit, offset)
    return total, [
        result(
            "skills",
            skill.id,
            str(
                cast(dict[str, Any], skill.payload.get("manifest") or {}).get("title")
                or skill.payload.get("name", "")
            ),
            str(
                cast(dict[str, Any], skill.payload.get("manifest") or {}).get("description")
                or skill.payload.get("content", "")
            ),
            q,
            created_at=skill.created_at.isoformat(),
            agent_id=skill.agent_id,
            enabled=bool(skill.payload.get("enabled", True)),
        )
        for (skill,) in rows
    ]


SEARCHERS = {
    "chats": search_chats,
    "messages": search_messages,
    "tasks": search_tasks,
    "files": search_files,
    "knowledge": search_knowledge,
    "skills": search_skills,
}


async def owner_search(
    session: AsyncSession,
    owner_id: str,
    q: str,
    category: SearchCategory | None = None,
    limit: int = 32,
    offset: int = 0,
) -> dict[str, Any]:
    """Owner-wide search for the owner API. Never expose it to an agent."""
    q = " ".join(q.split())
    categories = (category,) if category else SEARCH_CATEGORIES
    counts: dict[str, int] = {}
    results: dict[str, list[dict[str, Any]]] = {}
    for name in categories:
        counts[name], results[name] = await SEARCHERS[name](session, owner_id, q, limit, offset)
    return {
        "q": q,
        "category": category,
        "limit": limit,
        "offset": offset,
        "counts": counts,
        "results": results,
    }
