"""Mandate 13.1 and P5: knowledge notes have a chat path.

Notes were saved only from a page outside conversations. The owner now asks in chat and the
agent adds, lists or removes the note. An agent manages its own notes; Lonora, the lead,
manages any agent's (3.1.6, 3.2.4: an agent's memory is private to itself, Lonora and the
owner).
"""

from pathlib import Path
from typing import Any, cast
from uuid import uuid4

import pytest
from lonora_db.client import Database
from lonora_db.schema import AgentRow, SemanticMemoryRow
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from sqlalchemy import select
from test_task_runtime import task_db as task_db

Fixture = tuple[Database, str, str, str]


def context(fixture: Fixture, agent_id: str) -> ToolContext:
    db, owner, _, thread = fixture
    router = cast(Any, type("Router", (), {"credentials": None})())
    return ToolContext(
        db,
        owner,
        agent_id,
        thread,
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
        cast(Any, None),
        router,
        Path("/tmp/knowledge-tool-fixture"),
    )


async def agent(db: Database, owner: str, name: str, role: str = "specialist") -> str:
    async with db.sessions() as session, session.begin():
        row = AgentRow(owner_id=owner, name=name, role=role)
        session.add(row)
        await session.flush()
        return row.id


def test_the_note_tools_are_memory_tools_with_no_money_authority() -> None:
    tools = load_tools().tools
    for name in ("knowledge_note_add", "knowledge_note_list", "knowledge_note_delete"):
        assert tools[name].toolset == "memory" and not tools[name].financial
    assert tools["knowledge_note_list"].read_only
    assert not tools["knowledge_note_add"].read_only


@pytest.mark.asyncio
async def test_an_agent_adds_lists_and_removes_its_own_note(task_db: Fixture) -> None:
    db, owner, own, _ = task_db
    tools = load_tools().tools
    added = await tools["knowledge_note_add"].handler(
        context(task_db, own),
        {"title": "Gold rule", "content": "Scale into gold only after the London open."},
    )
    assert added["ok"] is True and added["indexed"] is True
    listed = await tools["knowledge_note_list"].handler(context(task_db, own), {})
    assert [(item["title"], item["content"]) for item in listed["notes"]] == [
        ("Gold rule", "Scale into gold only after the London open.")
    ]
    # Saving the same text again is the same note, not a duplicate.
    again = await tools["knowledge_note_add"].handler(
        context(task_db, own), {"content": "Scale into gold only after the London open."}
    )
    assert again["id"] == added["id"]
    removed = await tools["knowledge_note_delete"].handler(
        context(task_db, own), {"note_id": added["id"]}
    )
    assert removed == {"ok": True, "deleted": True}
    async with db.sessions() as session:
        assert list(await session.scalars(select(SemanticMemoryRow))) == []
    gone = await tools["knowledge_note_delete"].handler(
        context(task_db, own), {"note_id": added["id"]}
    )
    assert gone == {"ok": False, "code": "knowledge_note_not_found"}


@pytest.mark.asyncio
async def test_only_lonora_manages_another_agents_notes(task_db: Fixture) -> None:
    db, owner, own, _ = task_db
    tools = load_tools().tools
    lonora = await agent(db, owner, "Lonora", role="personal")
    peer = await agent(db, owner, "Peer")
    # A team agent cannot write or read a peer's notes (3.2.4).
    refused = await tools["knowledge_note_add"].handler(
        context(task_db, own), {"content": "A note for the peer", "agent_id": peer}
    )
    assert refused == {"ok": False, "code": "knowledge_note_agent_not_allowed"}
    hidden = await tools["knowledge_note_list"].handler(context(task_db, own), {"agent_id": peer})
    assert hidden == {"ok": False, "code": "knowledge_note_agent_not_allowed"}
    # Lonora, the lead, manages any agent's notes.
    added = await tools["knowledge_note_add"].handler(
        context(task_db, lonora), {"content": "A note for the peer", "agent_id": peer}
    )
    assert added["ok"] is True
    listed = await tools["knowledge_note_list"].handler(
        context(task_db, lonora), {"agent_id": peer}
    )
    assert [item["id"] for item in listed["notes"]] == [added["id"]]
    unknown = await tools["knowledge_note_list"].handler(
        context(task_db, lonora), {"agent_id": uuid4().hex}
    )
    assert unknown == {"ok": False, "code": "agent_not_found"}
