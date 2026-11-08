"""Agent-private memory, scoped session search and granular memory edits.

The pure cases run everywhere. The isolation and full-text cases use the real
tool registry on PostgreSQL (LONORA_DATABASE_URL) and prove that one Agent
cannot read another Agent's memory, private threads, groups or decisions.
"""

import os
from typing import Any

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_db.events import emit
from lonora_db.schema import MemoryRow, MessageRow, ThreadRow
from lonora_db.trading_decisions import DECISION_KIND
from lonora_memory.edits import (
    MEMORY_CHAR_LIMIT,
    MemoryEdit,
    MemoryEditError,
    MemoryOverflow,
    apply_edits,
)
from lonora_memory.profile import profile_documents
from lonora_memory.sessions import excerpt, literal_terms
from lonora_tools.loader import load_tools
from lonora_tools.memory import MemoryWrite
from lonora_tools.session_search import SessionSearchInput
from pydantic import ValidationError

DOCUMENT = (
    "Legacy fact one.\n\n# USER.md\n- Prefers Arabic replies\n- Concise\n\n"
    "# MEMORY.md\n- XAUUSD spreads widen at rollover\n"
)


# --- Granular memory edits (pure) ---------------------------------------------------


def test_batch_adds_patches_and_removes_entries_by_section():
    content, applied = apply_edits(
        DOCUMENT,
        [
            MemoryEdit("add", "USER.md", "- Timezone Asia/Riyadh"),
            MemoryEdit("add", "MEMORY.md", "- EURUSD.a trades 0.01 lots"),
            MemoryEdit("patch", old_text="Concise", content="Very concise"),
            MemoryEdit("remove", old_text="rollover"),
        ],
        3,
    )
    views = profile_documents(content)
    assert views["USER.md"] == "- Prefers Arabic replies\n- Very concise\n- Timezone Asia/Riyadh"
    assert views["memory/MEMORY.md"] == "Legacy fact one.\n\n- EURUSD.a trades 0.01 lots"
    assert "XAUUSD" not in content and content.endswith("\n")
    assert [item["changed"] for item in applied] == [True, True, True, True]


def test_add_creates_missing_sections_and_keeps_legacy_text_as_memory():
    empty, _ = apply_edits("", [MemoryEdit("add", "USER.md", "Name: Sam")], 1)
    assert empty == "# USER.md\nName: Sam\n"
    legacy, _ = apply_edits(
        "plain legacy\n",
        [MemoryEdit("add", "MEMORY.md", "fact two"), MemoryEdit("add", "USER.md", "pref")],
        1,
    )
    assert profile_documents(legacy) == {
        "memory/MEMORY.md": "plain legacy\n\nfact two",
        "USER.md": "pref",
    }


def test_duplicate_add_is_reported_unchanged():
    content, applied = apply_edits(DOCUMENT, [MemoryEdit("add", "USER.md", "- Concise")], 3)
    assert content == DOCUMENT and applied == [
        {"action": "add", "section": "USER.md", "changed": False}
    ]


@pytest.mark.parametrize(
    ("edit", "code", "details"),
    [
        (MemoryEdit("patch", old_text="absent text", content="x"), "memory_edit_no_match", {}),
        (MemoryEdit("patch", old_text="- ", content="x"), "memory_edit_ambiguous", {"matches": 4}),
        (MemoryEdit("remove", old_text="# USER.md"), "memory_edit_heading_protected", {}),
        (
            MemoryEdit("patch", old_text="Concise", content="Concise\n# MEMORY.md\nx"),
            "memory_edit_heading_protected",
            {},
        ),
    ],
)
def test_rejected_operation_names_its_index_and_cause(
    edit: MemoryEdit, code: str, details: dict[str, Any]
):
    with pytest.raises(MemoryEditError) as raised:
        apply_edits(DOCUMENT, [MemoryEdit("add", "USER.md", "- new"), edit], 3)
    result = raised.value.result()
    assert result["ok"] is False and result["code"] == code
    assert result["operation_index"] == 1
    assert details.items() <= result.items()


def test_no_match_suggests_the_closest_lines():
    with pytest.raises(MemoryEditError) as raised:
        apply_edits(DOCUMENT, [MemoryEdit("remove", old_text="Prefers English replies")], 3)
    assert raised.value.result()["closest_lines"][0] == "- Prefers Arabic replies"


def test_overlapping_occurrences_are_ambiguous():
    with pytest.raises(MemoryEditError) as raised:
        apply_edits("1000\n", [MemoryEdit("patch", old_text="00", content="x")], 1)
    assert raised.value.result()["matches"] == 2


def test_overflow_reports_size_and_shortfall_and_a_freeing_batch_fits():
    full = "# MEMORY.md\n" + "\n".join(f"- old fact {i:05d} " + "x" * 80 for i in range(320))
    full = full[: MEMORY_CHAR_LIMIT - 10] + "\n"
    with pytest.raises(MemoryOverflow) as raised:
        apply_edits(full, [MemoryEdit("add", content="- new fact " + "y" * 200)], 7)
    result = raised.value.result()
    assert result["code"] == "memory_too_large" and result["version"] == 7
    assert result["current_chars"] == len(full) and result["limit"] == MEMORY_CHAR_LIMIT
    assert result["shortfall"] == result["resulting_chars"] - MEMORY_CHAR_LIMIT > 0
    # The limit applies to the batch result: removing stale facts makes room.
    freed, _ = apply_edits(
        full,
        [
            MemoryEdit("remove", old_text="- old fact 00001 "),
            MemoryEdit("remove", old_text="- old fact 00002 "),
            MemoryEdit("remove", old_text="- old fact 00003 "),
            MemoryEdit("add", content="- new fact " + "y" * 200),
        ],
        7,
    )
    assert len(freed) <= MEMORY_CHAR_LIMIT and "new fact" in freed


def test_memory_write_accepts_exactly_one_shape():
    assert MemoryWrite.model_validate({"version": 1, "content": ""}).content == ""
    ops = MemoryWrite.model_validate(
        {"version": 1, "operations": [{"action": "add", "content": "fact"}]}
    )
    assert ops.operations[0].section == "MEMORY.md"
    for invalid in (
        {"version": 1},
        {"version": 1, "content": "x", "operations": [{"action": "add", "content": "y"}]},
        {"version": 1, "operations": [{"action": "patch", "content": "y"}]},
        {"version": 1, "operations": [{"action": "add", "content": "  "}]},
    ):
        with pytest.raises(ValidationError):
            MemoryWrite.model_validate(invalid)


# --- Session search shapes (pure) ----------------------------------------------------


def test_session_search_shape_requires_a_thread_for_scroll_and_read():
    assert SessionSearchInput.model_validate({}).limit == 10
    for invalid in (
        {"around_seq": 3},
        {"after_seq": 2},
        {"thread_id": "t", "around_seq": 1, "after_seq": 1},
    ):
        with pytest.raises(ValidationError):
            SessionSearchInput.model_validate(invalid)


def test_literal_terms_keep_symbols_and_excerpts_center_on_the_match():
    assert {"XAUUSDm", "order_123"} <= set(literal_terms("why XAUUSDm order_123 failed"))
    text = "a" * 2000 + " XAUUSDm breakout " + "b" * 2000
    snippet, cut = excerpt(text, "XAUUSDm")
    assert cut and "XAUUSDm breakout" in snippet and len(snippet) < 600


def test_session_search_is_core_and_search_internal_is_not_eager():
    catalog = load_tools()
    tool = catalog.tools["session_search"]
    assert tool.read_only and "core" in tool.eager and tool.toolset == "memory"
    assert not catalog.tools["search_internal"].eager


# --- PostgreSQL isolation, ranking and memory edits ----------------------------------


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Scoped history search uses PostgreSQL full-text functions.")


async def add_messages(fixture: Any, thread_id: str, messages: list[tuple[str, str | None, str]]):
    async with fixture.runtime.db.sessions() as session, session.begin():
        thread = await session.get(ThreadRow, thread_id, with_for_update=True)
        assert thread is not None
        for role, agent_id, content in messages:
            session.add(
                MessageRow(
                    thread_id=thread_id,
                    seq=thread.next_seq,
                    role=role,
                    agent_id=agent_id,
                    content=content,
                )
            )
            thread.next_seq += 1


async def set_memory(fixture: Any, agent_id: str, content: str) -> None:
    async with fixture.runtime.db.sessions() as session, session.begin():
        row = await session.get(MemoryRow, agent_id)
        assert row is not None
        row.content = content


async def record_decision(fixture: Any, agent_id: str, thread_id: str, summary: str) -> None:
    async with fixture.runtime.db.sessions() as session, session.begin():
        emit(
            session,
            fixture.owner,
            DECISION_KIND,
            thread_id=thread_id,
            agent_id=agent_id,
            payload={
                "decision": {
                    "id": "decision-" + agent_id,
                    "symbol": "XAUUSDm",
                    "account_id": "acct",
                    "timeframe": "H1",
                    "action": "WAIT",
                    "summary": summary,
                    "recorded_at": "2026-11-01T10:00:00+00:00",
                    "run_id": "run-" + agent_id,
                }
            },
        )


def texts(result: dict[str, Any]) -> str:
    return repr(result)


async def search(registry: Any, context: Any, call_id: str, **arguments: Any) -> dict[str, Any]:
    return await registry.execute(
        ToolCall(id=call_id, name="session_search", arguments=arguments), context, read_only=True
    )


@pytest.mark.asyncio
async def test_agents_cannot_read_each_others_memory_threads_groups_or_decisions():
    database()
    from check_streaming import Fixture
    from lonora_core.user_error import LonoraError

    fixture = await Fixture().open()
    try:
        alpha, bravo, charlie = (
            await fixture.agent("Alpha"),
            await fixture.agent("Bravo"),
            await fixture.agent("Charlie"),
        )
        alpha_thread = await fixture.conversation(alpha)
        bravo_thread = await fixture.conversation(bravo)
        shared = await fixture.request(
            "POST", "/groups/create", {"name": "AC", "member_ids": [alpha["id"], charlie["id"]]}
        )
        private = await fixture.request(
            "POST", "/groups/create", {"name": "BC", "member_ids": [bravo["id"], charlie["id"]]}
        )
        for group in (shared, private):
            fixture.groups.append(group["id"])
            fixture.group_threads.append(group["thread_id"])
        await set_memory(fixture, alpha["id"], "# MEMORY.md\n- sentinel alpha memory\n")
        await set_memory(fixture, bravo["id"], "# MEMORY.md\n- sentinel bravo private memory\n")
        await add_messages(
            fixture, alpha_thread["id"], [("user", None, "sentinel alpha conversation")]
        )
        await add_messages(
            fixture, bravo_thread["id"], [("user", None, "sentinel bravo private conversation")]
        )
        await add_messages(
            fixture, shared["thread_id"], [("user", None, "sentinel shared group note")]
        )
        await add_messages(
            fixture, private["thread_id"], [("user", None, "sentinel bravo charlie group")]
        )
        await record_decision(fixture, alpha["id"], alpha_thread["id"], "sentinel alpha wait")
        await record_decision(fixture, bravo["id"], bravo_thread["id"], "sentinel bravo wait")

        registry = load_tools()
        context = await fixture.lease(await fixture.run(alpha, alpha_thread))

        literal = await registry.execute(
            ToolCall(id="s1", name="search_internal", arguments={"query": "sentinel"}), context
        )
        assert [item["agent_id"] for item in literal["memory"]] == [alpha["id"]]
        assert {item["thread_id"] for item in literal["messages"]} == {
            alpha_thread["id"],
            shared["thread_id"],
        }
        assert "bravo" not in texts(literal)

        ranked = await search(registry, context, "s2", query="sentinel")
        assert ranked["mode"] == "discover" and ranked["authority"] == "historical_record"
        assert {item["thread_id"] for item in ranked["results"]} == {
            alpha_thread["id"],
            shared["thread_id"],
        }
        assert [item["decision_id"] for item in ranked["decisions"]] == ["decision-" + alpha["id"]]
        assert "bravo" not in texts(ranked)
        browsed = await search(registry, context, "s3")
        assert {item["thread_id"] for item in browsed["threads"]} == {
            alpha_thread["id"],
            shared["thread_id"],
        }
        for arguments in (
            {"thread_id": bravo_thread["id"]},
            {"thread_id": private["thread_id"], "around_seq": 1},
            {"thread_id": bravo_thread["id"], "query": "sentinel"},
        ):
            # Never revealed, even as existence: the same code as a missing thread.
            with pytest.raises(LonoraError) as hidden:
                await search(registry, context, "s4", **arguments)
            assert hidden.value.code == "thread_not_found"

        # Charlie belongs to both groups and sees both, but neither private conversation.
        charlie_context = await fixture.lease(
            await fixture.run(charlie, await fixture.conversation(charlie))
        )
        seen = await search(registry, charlie_context, "s5", query="sentinel")
        assert {item["thread_id"] for item in seen["results"]} == {
            shared["thread_id"],
            private["thread_id"],
        }
        assert seen["decisions"] == []

        # The owner API remains owner-wide by design.
        owner = await fixture.request("GET", "/search?q=sentinel")
        assert {item["agent_id"] for item in owner["memory"]} >= {alpha["id"], bravo["id"]}
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_subagent_searches_with_its_parent_agents_scope():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        parent, other = await fixture.agent("Parent"), await fixture.agent("Other")
        thread = await fixture.conversation(parent)
        other_thread = await fixture.conversation(other)
        await add_messages(fixture, thread["id"], [("user", None, "subscope parent finding")])
        await add_messages(fixture, other_thread["id"], [("user", None, "subscope other secret")])
        await set_memory(fixture, other["id"], "- subscope other memory\n")
        registry = load_tools()
        context = await fixture.lease(await fixture.run(parent, thread))
        child = await registry.execute(
            ToolCall(id="spawn-1", name="subagent_spawn", arguments={"task": "Review findings"}),
            context,
        )
        assert child["agent_id"] == parent["id"]
        child_context = await fixture.lease(child)
        found = await search(registry, child_context, "c1", query="subscope")
        assert [item["thread_id"] for item in found["results"]] == [thread["id"]]
        literal = await registry.execute(
            ToolCall(id="c2", name="search_internal", arguments={"query": "subscope"}),
            child_context,
            read_only=True,
        )
        assert "other" not in texts(literal["messages"]) and literal["memory"] == []
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_full_text_ranking_identifiers_scroll_and_read_pages():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Ranker")
        thread = await fixture.conversation(agent)
        filler = [("user", None, f"routine note {index}") for index in range(1, 26)]
        await add_messages(
            fixture,
            thread["id"],
            [
                ("user", None, "Gold looked strong today."),
                ("assistant", agent["id"], "The gold breakout held above resistance on XAUUSDm."),
                ("user", None, "Any breakout elsewhere?"),
                *filler,
                ("user", None, "Order ord-77f2 was rejected by the broker."),
                ("user", None, "long " + "z" * 3000),
            ],
        )
        registry = load_tools()
        context = await fixture.lease(await fixture.run(agent, thread))
        ranked = await search(registry, context, "r1", query="gold breakout")
        assert ranked["match"] == "full_text"
        first = ranked["results"][0]
        assert first["seq"] == 2 and first["role"] == "assistant" and first["author"] == "self"
        assert {"thread_id", "seq", "message_id", "created_at"} <= first.keys()
        loose = await search(registry, context, "r1b", query="gold unrelatedword")
        assert loose["match"] == "full_text_any_word"
        assert {item["seq"] for item in loose["results"]} == {1, 2}
        symbol = await search(registry, context, "r2", query="XAUUSDm")
        assert [item["seq"] for item in symbol["results"]] == [2]
        identifier = await search(registry, context, "r3", query="ord-77f2")
        assert [item["seq"] for item in identifier["results"]] == [29]
        window = await search(
            registry, context, "r4", thread_id=thread["id"], around_seq=2, limit=4
        )
        assert [item["seq"] for item in window["messages"]] == [1, 2, 3, 4]
        page = await search(registry, context, "r5", thread_id=thread["id"], limit=10)
        assert [item["seq"] for item in page["messages"]] == list(range(1, 11))
        assert page["next_after_seq"] == 10
        last = await search(registry, context, "r6", thread_id=thread["id"], after_seq=29)
        assert [item["seq"] for item in last["messages"]] == [30]
        assert last["messages"][0]["truncated"] and len(last["messages"][0]["text"]) == 2000
        assert last["next_after_seq"] is None
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_memory_operations_commit_atomically_with_receipts_and_overflow_protocol():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Memory editor")
        thread = await fixture.conversation(agent)
        await set_memory(fixture, agent["id"], DOCUMENT)
        registry = load_tools()
        context = await fixture.lease(await fixture.run(agent, thread))
        operations = [
            {"action": "add", "section": "USER.md", "content": "- Timezone Asia/Riyadh"},
            {"action": "patch", "old_text": "Concise", "content": "Very concise"},
        ]
        call = ToolCall(
            id="m1", name="memory_write", arguments={"version": 1, "operations": operations}
        )
        saved = await registry.execute(call, context)
        assert saved["version"] == 2 and "content" not in saved
        assert saved["chars"] < MEMORY_CHAR_LIMIT and len(saved["applied"]) == 2
        # Crash replay of the same call returns its receipt instead of applying twice.
        assert await registry.execute(call, context) == saved
        current = await registry.execute(
            ToolCall(id="m2", name="memory_read", arguments={}), context, read_only=True
        )
        assert current["version"] == 2 and current["content"].count("Timezone") == 1

        rejected = await registry.execute(
            ToolCall(
                id="m3",
                name="memory_write",
                arguments={
                    "version": 2,
                    "operations": [
                        {"action": "add", "content": "- kept only if all succeed"},
                        {"action": "remove", "old_text": "absent"},
                    ],
                },
            ),
            context,
        )
        assert rejected["ok"] is False and rejected["code"] == "memory_edit_no_match"
        assert rejected["operation_index"] == 1
        conflict = await registry.execute(
            ToolCall(
                id="m4",
                name="memory_write",
                arguments={"version": 1, "operations": [{"action": "add", "content": "- x"}]},
            ),
            context,
        )
        assert conflict == {
            "ok": False,
            "code": "version_conflict",
            "version": 2,
            "chars": saved["chars"],
        }
        overflow = await registry.execute(
            ToolCall(
                id="m5",
                name="memory_write",
                arguments={
                    "version": 2,
                    "operations": [
                        {"action": "add", "content": "a" * 8000},
                        {"action": "add", "content": "b" * 8000},
                        {"action": "add", "content": "c" * 8000},
                        {"action": "add", "content": "d" * 8000},
                    ],
                },
            ),
            context,
        )
        assert overflow["code"] == "memory_too_large" and overflow["shortfall"] > 0
        assert overflow["current_chars"] == saved["chars"]
        async with fixture.runtime.db.sessions() as session:
            row = await session.get(MemoryRow, agent["id"])
            assert row is not None and row.version == 2 and "kept only" not in row.content
        # Whole-document replace keeps its original contract.
        replaced = await registry.execute(
            ToolCall(id="m6", name="memory_write", arguments={"version": 2, "content": "fresh"}),
            context,
        )
        assert replaced["version"] == 3 and replaced["content"] == "fresh\n"
    finally:
        await fixture.close()
