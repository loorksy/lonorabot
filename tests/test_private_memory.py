"""A team agent's memory is private to itself, Lonora and the owner (3.2.4).

"Memory lives in Lonora's memory store, never in workspace files, which all agents
share." The PostgreSQL case reads one team agent's memory through every path an
agent has (memory_read, search_internal, session_search, subagent_inspect,
agent_inspect): the agent itself and Lonora reach it, another team agent never does,
and the owner reads it through the owner API. The static case pins that no workspace
module reads or writes the memory store, so nothing exports memory into shared files.
"""

import ast
import json
import os
from pathlib import Path
from typing import Any
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_core.user_error import LonoraError
from lonora_tools.loader import load_tools

ROOT = Path(__file__).resolve().parents[1]
SENTINEL = "privatesentinel" + uuid4().hex[:6]
# Everything that reads or writes an agent's memory or the owner profile.
MEMORY_STORE = {
    "MemoryRow",
    "MemoryRevisionRow",
    "OwnerProfileRow",
    "read_memory",
    "commit_memory",
    "memory_view",
    "atomic_commit",
    "atomic_edit",
    "read_owner_profile",
    "commit_owner_profile",
}


def workspace_modules() -> list[Path]:
    return sorted(
        path
        for base in ("packages", "apps")
        for path in (ROOT / base).glob("*/src/**/*.py")
        # Any module whose path names the workspace, including a workspace package.
        if "workspace" in str(path.relative_to(ROOT))
    )


def test_no_workspace_module_touches_the_memory_store():
    modules = workspace_modules()
    assert modules, "the workspace modules moved; point this test at them"
    for path in modules:
        tree = ast.parse(path.read_text())
        names = {
            alias.asname or alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            for alias in node.names
        } | {node.id for node in ast.walk(tree) if isinstance(node, ast.Name)}
        assert not names & MEMORY_STORE, (path, names & MEMORY_STORE)
        text = path.read_text()
        for document in ("MEMORY.md", "OPERATING.md", "USER.md"):
            assert document not in text, (path, document)


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Memory privacy reads use PostgreSQL full-text search.")


async def call(context: Any, name: str, **arguments: Any) -> dict[str, Any]:
    result = await load_tools().execute(
        ToolCall(id="call-" + uuid4().hex, name=name, arguments=arguments), context
    )
    json.dumps(result)
    return result


async def refused(context: Any, name: str, **arguments: Any) -> str:
    try:
        result = await call(context, name, **arguments)
    except LonoraError as error:
        return error.code
    return str(result.get("code"))


async def wake(fixture: Any, agent_id: str) -> Any:
    """A routine run of the agent in its own conversation."""
    from lonora_contracts.runs import RunRequest
    from lonora_db.runs import create_run
    from lonora_db.threads import conversation_thread

    async with fixture.runtime.db.sessions() as session, session.begin():
        thread = await conversation_thread(session, fixture.owner, agent_id)
        run = await create_run(
            session,
            fixture.owner,
            RunRequest(thread_id=thread.id, agent_id=agent_id, trigger="routine", prompt="Check"),
        )
        data = {"id": run.id, "agent_id": agent_id, "thread_id": thread.id}
    return await fixture.lease(data)


@pytest.mark.asyncio
async def test_a_team_agents_memory_reaches_itself_lonora_and_the_owner_only():
    database()
    from check_streaming import Fixture
    from lonora_db.personal_agent import ensure_personal_agent
    from lonora_db.schema import MemoryRow, MessageRow, ThreadRow

    fixture = await Fixture().open()
    try:
        gold, euro = await fixture.agent("Gold"), await fixture.agent("Euro")
        async with fixture.runtime.db.sessions() as session, session.begin():
            lonora = (await ensure_personal_agent(session, fixture.owner)).id
            row = await session.get(MemoryRow, gold["id"])
            assert row is not None
            row.content = f"# MEMORY.md\n- {SENTINEL} gold spreads widen at the open\n"
        gold_thread = await fixture.conversation(gold)
        async with fixture.runtime.db.sessions() as session, session.begin():
            thread = await session.get(ThreadRow, gold_thread["id"], with_for_update=True)
            assert thread is not None
            session.add(
                MessageRow(
                    thread_id=thread.id,
                    seq=thread.next_seq,
                    role="assistant",
                    agent_id=gold["id"],
                    content=f"{SENTINEL} I skipped the London entry",
                )
            )
            thread.next_seq += 1
        gold_run = await fixture.run(gold, gold_thread)
        mine, lead, peer = (
            await wake(fixture, gold["id"]),
            await wake(fixture, lonora),
            await wake(fixture, euro["id"]),
        )
        # The agent itself.
        own = await call(mine, "memory_read")
        assert SENTINEL in own["content"]
        # Another team agent: memory_read is its own document only, and every other path
        # reads as not found or empty.
        other = await call(peer, "memory_read")
        assert SENTINEL not in json.dumps(other)
        literal = await call(peer, "search_internal", query=SENTINEL)
        assert literal["memory"] == [] and literal["messages"] == []
        found = await call(peer, "session_search", query=SENTINEL)
        assert found["results"] == []
        assert await refused(peer, "session_search", thread_id=gold_thread["id"]) == (
            "thread_not_found"
        )
        assert await refused(peer, "subagent_inspect", run_id=gold_run["id"]) == "run_not_found"
        assert await refused(peer, "agent_inspect", agent_id=gold["id"], section="memory") != (
            "None"
        )
        # Lonora reads the team agent's memory and work, labelled as untrusted records.
        literal = await call(lead, "search_internal", query=SENTINEL)
        assert [item["agent_id"] for item in literal["memory"]] == [gold["id"]]
        assert literal["memory"][0]["untrusted"] is True
        found = await call(lead, "session_search", query=SENTINEL)
        assert {item["thread_id"] for item in found["results"]} == {gold_thread["id"]}
        page = await call(lead, "agent_inspect", agent_id=gold["id"], section="memory")
        assert SENTINEL in page["memory"] and page["editable"] is False
        # The owner reads it through the owner API.
        memory = await fixture.request("GET", f"/agents/{gold['id']}/memory")
        assert SENTINEL in memory["content"]
    finally:
        await fixture.close()
