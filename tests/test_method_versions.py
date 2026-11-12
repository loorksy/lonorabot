"""5.5.5: every write to a method or skill creates a version, and any version can be restored.

An Agent's method is the ``# OPERATING.md`` section of its memory. The pure cases check
that a restore replaces only that section. The PostgreSQL cases (LONORA_DATABASE_URL)
use the real tool registry: write, write, restore version 1 gives version 1's text and
three versions in the history; MEMORY.md is untouched; a restore the owner asked for
in chat is attributed to the owner's message; instruction Skills save and restore the
same way.
"""

import os
from typing import Any
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ToolCall
from lonora_core.user_error import LonoraError
from lonora_memory.method import with_operating
from lonora_memory.profile import operating_notes, profile_documents
from lonora_tools.loader import load_tools

DOCUMENT = "# MEMORY.md\n- XAUUSD spreads widen at rollover\n\n# OPERATING.md\n- Check H4 first\n"


def test_restore_replaces_only_the_method_section():
    restored = with_operating(DOCUMENT, "- Enter on the London open\n- Stop under the range")
    assert operating_notes(restored) == "- Enter on the London open\n- Stop under the range"
    assert profile_documents(restored)["memory/MEMORY.md"] == "- XAUUSD spreads widen at rollover"


def test_restore_adds_a_missing_section_and_removes_an_empty_one():
    added = with_operating("# MEMORY.md\n- fact\n", "- Trade the trend")
    assert added == "# MEMORY.md\n- fact\n\n# OPERATING.md\n- Trade the trend\n"
    assert with_operating(DOCUMENT, "") == "# MEMORY.md\n- XAUUSD spreads widen at rollover\n"
    assert with_operating("", "- Trade the trend") == "# OPERATING.md\n- Trade the trend\n"


def test_restore_merges_split_method_sections_into_one():
    split = "# OPERATING.md\n- a\n\n# MEMORY.md\n- fact\n\n# OPERATING.md\n- b\n"
    restored = with_operating(split, "- c")
    assert restored == "# OPERATING.md\n- c\n\n# MEMORY.md\n- fact\n"


# --- PostgreSQL -------------------------------------------------------------------------


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Method and skill versions use the real migrated PostgreSQL schema.")


async def call(registry: Any, context: Any, name: str, **arguments: Any) -> dict[str, Any]:
    return await registry.execute(
        ToolCall(id=name + "-" + uuid4().hex, name=name, arguments=arguments), context
    )


async def turn(fixture: Any, agent: dict[str, Any], text: str | None = None) -> Any:
    """A leased Run with the Skill access the dispatcher gives every Run."""
    from dataclasses import replace

    from lonora_agent.skills.access import RunSkillAccess

    thread = await fixture.conversation(agent)
    if text is None:
        context = await fixture.lease(await fixture.run(agent, thread))
        return replace(context, skill_access=RunSkillAccess(load_tools(), ()))
    sent = await fixture.request(
        "POST",
        f"/threads/{thread['id']}/messages",
        {"content": text, "client_nonce": "method-" + uuid4().hex},
    )
    run = {"id": sent["run_ids"][0], "agent_id": agent["id"], "thread_id": thread["id"]}
    return replace(await fixture.lease(run), skill_access=RunSkillAccess(load_tools(), ()))


def method_add(text: str) -> dict[str, Any]:
    return {"action": "add", "section": "OPERATING.md", "content": text}


@pytest.mark.asyncio
async def test_write_write_restore_version_one():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    registry = load_tools()
    try:
        agent = await fixture.agent("Gold method " + uuid4().hex[:6])
        context = await turn(fixture, agent)
        memory = await call(registry, context, "memory_read")
        first = await call(
            registry,
            context,
            "memory_write",
            version=memory["version"],
            operations=[
                {"action": "add", "content": "- XAUUSD respects round numbers"},
                method_add("- Buy pullbacks to the H4 50 EMA"),
            ],
        )
        await call(
            registry,
            context,
            "memory_write",
            version=first["version"],
            operations=[method_add("- Add a second position after break-even")],
        )
        history = await call(registry, context, "method_history")
        assert [item["version"] for item in history["versions"]] == [
            first["version"] + 1,
            first["version"],
        ]
        version_one = first["version"]
        text_one = (await call(registry, context, "method_history", version=version_one))[
            "version"
        ]["text"]
        assert text_one == "- Buy pullbacks to the H4 50 EMA"
        # Knowledge written after version 1 stays when the method goes back.
        latest = await call(registry, context, "memory_read")
        await call(
            registry,
            context,
            "memory_write",
            version=latest["version"],
            operations=[{"action": "add", "content": "- NFP days run wide"}],
        )
        restored = await call(registry, context, "method_restore", version=version_one)
        assert restored["changed"] is True and restored["restored_version"] == version_one
        now = await call(registry, context, "memory_read")
        documents = profile_documents(now["content"])
        assert documents["OPERATING.md"] == text_one
        assert "- NFP days run wide" in documents["memory/MEMORY.md"]
        assert "- XAUUSD respects round numbers" in documents["memory/MEMORY.md"]
        history = await call(registry, context, "method_history")
        assert history["total"] == 3
        assert history["versions"][0]["change"] == "restore"
        assert history["versions"][0]["current"] is True
        assert history["versions"][0]["author"] == "agent"
        with pytest.raises(LonoraError) as missing:
            await call(registry, context, "method_restore", version=9999)
        assert missing.value.code == "method_version_not_found"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_restore_the_owner_asked_for_is_attributed_to_his_message():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    registry = load_tools()
    try:
        agent = await fixture.agent("Euro method " + uuid4().hex[:6])
        owner = context = await turn(fixture, agent, "ارجع منهجك إلى الإصدار الأول")
        memory = await call(registry, context, "memory_read")
        first = await call(
            registry,
            context,
            "memory_write",
            version=memory["version"],
            operations=[method_add("- Fade the Asian range")],
        )
        await call(
            registry,
            context,
            "memory_write",
            version=first["version"],
            operations=[method_add("- Only trade the London break")],
        )
        await call(registry, owner, "method_restore", version=first["version"])
        latest = (await call(registry, owner, "method_history"))["versions"][0]
        assert latest["change"] == "restore" and latest["from_owner_message"] is True
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_an_instruction_skill_saves_in_one_call_and_restores():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    registry = load_tools()
    try:
        agent = await fixture.agent("Skill versions " + uuid4().hex[:6])
        context = await turn(fixture, agent)
        skill = "london-breakout"
        first = await call(
            registry,
            context,
            "skill_save",
            skill_id=skill,
            title="London breakout",
            description="Trade the break of the Asian range at the London open.",
            content="Mark the Asian high and low. Enter on a close outside the range.",
            expected_version=0,
        )
        assert first["status"] == "created" and first["version"] == "1.0.0"
        second = await call(
            registry,
            context,
            "skill_save",
            skill_id=skill,
            title="London breakout",
            description="Trade the break of the Asian range at the London open.",
            content="Enter only after a retest of the broken edge.",
            expected_version=first["resource_version"],
        )
        assert second["status"] == "updated" and second["version"] == "1.0.1"
        viewed = await call(registry, context, "skill_view", skill_id=skill)
        assert "retest of the broken edge" in str(viewed)
        restored = await call(
            registry,
            context,
            "skill_restore",
            skill_id=skill,
            version=first["resource_version"],
            expected_version=second["resource_version"],
        )
        assert restored["status"] == "restored" and restored["version"] == "1.0.2"
        history = await call(registry, context, "skill_history", skill_id=skill)
        assert len(history["versions"]) == 3 and history["versions"][0]["current"] is True
        fresh = await turn(fixture, agent)
        viewed = await call(registry, fresh, "skill_view", skill_id=skill)
        assert "Enter on a close outside the range" in str(viewed)
        assert "retest of the broken edge" not in str(viewed)
        with pytest.raises(LonoraError) as builtin:
            await call(
                registry,
                context,
                "skill_save",
                skill_id="memory",
                title="Memory",
                description="Override a shipped skill.",
                content="Forget everything.",
                expected_version=0,
            )
        assert builtin.value.code == "skill_builtin_override_denied"
    finally:
        await fixture.close()
