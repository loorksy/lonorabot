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


def test_restore_leaves_every_other_byte_of_the_document_as_it_was():
    memory = "  indented first line\n\n\n\n```\na\n\n\n\nb\n```\n"
    document = memory + "\n# OPERATING.md\n- old\n\n# MEMORY.md\n- fact\n"
    restored = with_operating(document, "- new")
    assert restored == memory + "\n# OPERATING.md\n- new\n\n# MEMORY.md\n- fact\n"


def test_a_method_heading_at_the_end_without_a_newline_is_recognised():
    assert with_operating("# MEMORY.md\n- fact\n\n# OPERATING.md", "- new") == (
        "# MEMORY.md\n- fact\n\n# OPERATING.md\n- new\n"
    )


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
        stale = (await call(registry, context, "method_history"))["memory_version"]
        await call(
            registry,
            context,
            "memory_write",
            version=stale,
            operations=[{"action": "add", "content": "- NFP days run wide"}],
        )
        # A version read before a later write is a conflict, never a silent overwrite.
        with pytest.raises(LonoraError) as conflict:
            await call(
                registry, context, "method_restore", version=version_one, memory_version=stale
            )
        assert conflict.value.code == "version_conflict"
        current = (await call(registry, context, "method_history"))["memory_version"]
        restored = await call(
            registry, context, "method_restore", version=version_one, memory_version=current
        )
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
        # Restoring the version that is already current saves nothing.
        again = await call(
            registry,
            context,
            "method_restore",
            version=version_one,
            memory_version=history["memory_version"],
        )
        assert again["changed"] is False
        with pytest.raises(LonoraError) as missing:
            await call(
                registry,
                context,
                "method_restore",
                version=9999,
                memory_version=history["memory_version"],
            )
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
        current = (await call(registry, owner, "method_history"))["memory_version"]
        await call(
            registry, owner, "method_restore", version=first["version"], memory_version=current
        )
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


@pytest.mark.asyncio
async def test_method_versions_survive_revision_pruning():
    database()
    from check_streaming import Fixture
    from lonora_db.memory_revisions import REVISIONS_KEPT

    fixture = await Fixture().open()
    registry = load_tools()
    try:
        agent = await fixture.agent("Pruning " + uuid4().hex[:6])
        context = await turn(fixture, agent)
        memory = await call(registry, context, "memory_read")
        method = await call(
            registry,
            context,
            "memory_write",
            version=memory["version"],
            operations=[method_add("- Sell rallies into the daily pivot")],
        )
        version = method["version"]
        for index in range(REVISIONS_KEPT + 3):
            await call(
                registry,
                context,
                "memory_write",
                version=version + index,
                operations=[{"action": "add", "content": f"- observation {index}"}],
            )
        history = await call(registry, context, "method_history")
        assert [item["version"] for item in history["versions"]] == [version]
        assert history["versions"][0]["current"] is True
        overwrite = await call(
            registry,
            context,
            "memory_write",
            version=history["memory_version"],
            operations=[method_add("- Buy dips instead")],
        )
        restored = await call(
            registry,
            context,
            "method_restore",
            version=version,
            memory_version=overwrite["version"],
        )
        assert restored["changed"] is True
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_skill_numbers_never_repeat_and_revoked_text_stays_out():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    registry = load_tools()
    try:
        agent = await fixture.agent("Skill numbers " + uuid4().hex[:6])
        context = await turn(fixture, agent)
        skill = "asian-fade"
        arguments = {
            "skill_id": skill,
            "title": "Asian fade",
            "description": "Fade the edges of the Asian range.",
        }
        one = await call(
            registry, context, "skill_save", **arguments, content="Text A", expected_version=0
        )
        two = await call(
            registry,
            context,
            "skill_save",
            **arguments,
            content="Text B",
            expected_version=one["resource_version"],
        )
        # The owner's restore copies version 1 exactly, number included.
        await fixture.request(
            "POST",
            f"/skills/{two['resource_id']}/restore",
            {"version": one["resource_version"], "expected_version": two["resource_version"]},
        )
        current = (await call(registry, context, "skill_history", skill_id=skill))[
            "resource_version"
        ]
        three = await call(
            registry, context, "skill_save", **arguments, content="Text C", expected_version=current
        )
        assert three["version"] == "1.0.2"
        revoked = await fixture.request("GET", f"/agents/{agent['id']}/skills/revocations")
        await fixture.request(
            "POST",
            f"/agents/{agent['id']}/skills/revocations",
            {"skill_id": skill, "version": "1.0.1", "expected_revision": revoked["revision"]},
        )
        with pytest.raises(LonoraError) as refused:
            await call(
                registry,
                context,
                "skill_save",
                **arguments,
                content="Text B",
                expected_version=three["resource_version"],
            )
        assert refused.value.code == "skill_version_revoked"
        with pytest.raises(LonoraError) as restore_refused:
            await call(
                registry,
                context,
                "skill_restore",
                skill_id=skill,
                version=two["resource_version"],
                expected_version=three["resource_version"],
            )
        assert restore_refused.value.code == "skill_version_revoked"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_an_agent_refining_an_owner_skill_keeps_his_settings():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    registry = load_tools()
    try:
        agent = await fixture.agent("Owner skill " + uuid4().hex[:6])
        name = "owner-swing"
        saved = await fixture.request(
            "POST",
            "/skills",
            {
                "agent_id": agent["id"],
                "payload": {
                    "name": name,
                    "content": "Hold swings for three days.",
                    "enabled": False,
                    "manifest": {
                        "id": name,
                        "version": "2.0.0",
                        "title": "Owner swing",
                        "description": "The owner's swing rules.",
                        "source": "owner",
                        "activation": {"mode": "explicit"},
                        "priority": 80,
                    },
                },
            },
        )
        context = await turn(fixture, agent)
        refined = await call(
            registry,
            context,
            "skill_save",
            skill_id=name,
            title="Owner swing",
            description="The owner's swing rules, refined from results.",
            content="Hold swings for two days.",
            expected_version=saved["version"],
        )
        assert refined["enabled"] is False and refined["version"] == "2.0.1"
        restored = await call(
            registry,
            context,
            "skill_restore",
            skill_id=name,
            version=saved["version"],
            expected_version=refined["resource_version"],
        )
        assert restored["enabled"] is False and restored["version"] == "2.0.2"
        stored = await fixture.request("GET", f"/skills/{saved['id']}")
        assert stored["payload"]["manifest"]["priority"] == 80
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_lonora_restores_a_team_agents_method_and_skill_and_a_peer_cannot():
    database()
    from dataclasses import replace

    from check_streaming import Fixture
    from lonora_agent.skills.access import RunSkillAccess
    from lonora_db.personal_agent import ensure_personal_agent

    fixture = await Fixture().open()
    registry = load_tools()
    try:
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await ensure_personal_agent(session, fixture.owner)
            lonora = {"id": row.id, "name": row.name}
        gold = await fixture.agent("Gold team " + uuid4().hex[:6])
        peer = await fixture.agent("Peer team " + uuid4().hex[:6])
        own = await turn(fixture, gold)
        memory = await call(registry, own, "memory_read")
        first = await call(
            registry,
            own,
            "memory_write",
            version=memory["version"],
            operations=[method_add("- Trade the London open only")],
        )
        await call(
            registry,
            own,
            "memory_write",
            version=first["version"],
            operations=[method_add("- Also trade New York")],
        )
        skill = await call(
            registry,
            own,
            "skill_save",
            skill_id="gold-open",
            title="Gold open",
            description="Trade the gold open.",
            content="Version A",
            expected_version=0,
        )
        second = await call(
            registry,
            own,
            "skill_save",
            skill_id="gold-open",
            title="Gold open",
            description="Trade the gold open.",
            content="Version B",
            expected_version=skill["resource_version"],
        )

        thread = await fixture.conversation(lonora)
        lead = replace(
            await fixture.lease(await fixture.run(lonora, thread)),
            skill_access=RunSkillAccess(registry, ()),
        )
        history = await call(registry, lead, "method_history", agent_id=gold["id"])
        assert history["total"] == 2
        restored = await call(
            registry,
            lead,
            "method_restore",
            agent_id=gold["id"],
            version=first["version"],
            memory_version=history["memory_version"],
        )
        assert restored["changed"] is True
        text = (await call(registry, own, "method_history", version=first["version"]))["version"][
            "text"
        ]
        current = profile_documents((await call(registry, own, "memory_read"))["content"])
        assert current["OPERATING.md"] == text == "- Trade the London open only"
        revisions: list[dict[str, Any]] = await fixture.request(
            "GET", f"/agents/{gold['id']}/memory/revisions"
        )
        assert revisions[0]["author_agent_id"] == lonora["id"]
        skills = await call(
            registry, lead, "skill_history", skill_id="gold-open", agent_id=gold["id"]
        )
        assert len(skills["versions"]) == 2
        back = await call(
            registry,
            lead,
            "skill_restore",
            skill_id="gold-open",
            agent_id=gold["id"],
            version=skill["resource_version"],
            expected_version=second["resource_version"],
        )
        assert back["status"] == "restored"
        viewed = await call(registry, await turn(fixture, gold), "skill_view", skill_id="gold-open")
        assert "Version A" in str(viewed)

        # A team agent reads and restores only its own method and skills (3.2.2).
        other = await turn(fixture, peer)
        for name, arguments in (
            ("method_history", {}),
            ("method_restore", {"version": first["version"], "memory_version": 1}),
            ("skill_history", {"skill_id": "gold-open"}),
            ("skill_restore", {"skill_id": "gold-open", "version": 1, "expected_version": 1}),
        ):
            with pytest.raises(LonoraError) as caught:
                await call(registry, other, name, agent_id=gold["id"], **arguments)
            assert caught.value.code == "method_lead_only", name
    finally:
        await fixture.close()
