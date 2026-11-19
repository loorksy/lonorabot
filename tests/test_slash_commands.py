"""The / commands of the composer (chat.composer.slash-commands) on the server.

The owner's message keeps its own words ("/search gold prices") and carries which command
they are. The server writes the chip on the message, the Agent's turn reads what was asked,
and /search preselects web_search. A command grants nothing.

The pure cases run everywhere. The PostgreSQL cases (LONORA_DATABASE_URL) go through the
owner API and the runtime on the migrated schema.
"""

import os
from typing import Any
from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from lonora_contracts.domain import MessageCommand, MessageCreate
from lonora_db.rich_response import server_rich_content, validated_rich_content
from lonora_tools.loader import load_tools
from pydantic import ValidationError
from test_task_runtime import task_db as task_db

SEARCH = {"name": "search", "argument": "أسعار الذهب"}


def test_a_command_is_shaped_by_its_name():
    assert MessageCommand(name="summary").argument == ""
    assert MessageCommand(name="skill", skill_id="s1", argument="").skill_id == "s1"
    for bad in (
        {"name": "search"},
        {"name": "task", "argument": "  "},
        {"name": "summary", "argument": "x"},
        {"name": "skill"},
        {"name": "search", "argument": "x", "skill_id": "s1"},
        {"name": "clear"},
    ):
        with pytest.raises(ValidationError):
            MessageCommand.model_validate(bad)


def test_a_command_message_is_plain_text_that_ends_with_its_argument():
    sent = MessageCreate.model_validate({"content": "‏/بحث أسعار الذهب ", "command": SEARCH})
    assert sent.command is not None and sent.command.argument == "أسعار الذهب"
    assert MessageCreate.model_validate({"content": "/ملخص", "command": {"name": "summary"}})
    for bad in (
        {"content": "بحث أسعار الذهب", "command": SEARCH},
        {"content": "/بحث أسعار الفضة", "command": SEARCH},
        {"content": "/بحث أسعار الذهب", "command": SEARCH, "attachment_ids": ["a"]},
        {"content": "/بحث أسعار الذهب", "command": SEARCH, "edited_from": "m1"},
    ):
        with pytest.raises(ValidationError, match="message_command_invalid"):
            MessageCreate.model_validate(bad)


def test_a_command_takes_text_as_long_as_the_message_it_ends():
    long = ("ذهب " * 2000).strip()  # More than a short field holds, less than a message.
    sent = MessageCreate.model_validate(
        {"content": "/task " + long, "command": {"name": "task", "argument": long}}
    )
    assert sent.command is not None and len(sent.command.argument) == len(long) > 4000
    part = {"type": "command", "name": "task", "argument": long}
    assert server_rich_content(part)["parts"][0]["argument"] == long


def test_only_the_server_writes_the_command_part():
    part = {"type": "command", **SEARCH}
    assert server_rich_content(part)["parts"] == [part]
    assert validated_rich_content({"version": 1, "parts": [part]}) is None


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The command cases use the real migrated PostgreSQL schema.")


async def send(fixture: Any, thread_id: str, body: dict[str, Any]) -> Any:
    return await fixture.client.post(
        f"/api/threads/{thread_id}/messages",
        json={"client_nonce": "cmd-" + uuid4().hex, **body},
    )


async def system_text(context: Any) -> str:
    from lonora_agent.context.builder import build_context

    return "\n".join(m.content for m in await build_context(context) if m.role == "system")


@pytest.mark.asyncio
async def test_search_is_kept_on_the_message_read_by_the_turn_and_preselects_web_search(
    monkeypatch: pytest.MonkeyPatch,
):
    database()
    from check_streaming import Fixture
    from lonora_agent.tool_exposure import ensure_exposure

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Commander")
        thread = await fixture.conversation(agent)
        response = await send(
            fixture, thread["id"], {"content": "/بحث أسعار الذهب", "command": SEARCH}
        )
        assert response.status_code == 202
        sent = response.json()
        assert sent["message"]["content"] == "/بحث أسعار الذهب"
        assert sent["message"]["rich_content"]["parts"] == [
            {"type": "command", "name": "search", "argument": "أسعار الذهب", "skill_id": None}
        ]
        assert len(sent["runs"]) == 1
        context = await fixture.lease({**sent["runs"][0], "thread_id": thread["id"]})
        system = await system_text(context)
        assert "is the /search command" in system

        def trading_profiles(*_a: object, **_k: object) -> list[str]:
            return ["core", "market"]

        monkeypatch.setattr("lonora_agent.tool_exposure.run_profiles", trading_profiles)
        registry = load_tools()
        monkeypatch.setattr(registry, "availability", AsyncMock(return_value={}))
        exposure = await ensure_exposure(
            context, registry, {}, [], [], scope="full", task_run=False
        )
        assert "web_search" in exposure["native"]

        # A later wake on the same thread reads the /search message at its input_seq: the
        # owner's command was for that message's own turn, never for a wake (§6.10).
        from lonora_db.schema import RunRow

        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(RunRow, context.lease.run_id)
            assert row is not None
            row.trigger = "wake"
        exposure = await ensure_exposure(
            context, registry, {}, [], [], scope="full", task_run=False
        )
        assert "web_search" not in exposure["native"]

        # A plain message is an ordinary turn.
        plain_thread = await fixture.conversation(await fixture.agent("Plain"))
        plain = (await send(fixture, plain_thread["id"], {"content": "وماذا عن الفضة؟"})).json()
        assert plain["message"]["rich_content"] is None
        context = await fixture.lease({**plain["runs"][0], "thread_id": plain_thread["id"]})
        assert "lonora_owner_command" not in await system_text(context)
        exposure = await ensure_exposure(
            context, registry, {}, [], [], scope="full", task_run=False
        )
        assert "web_search" not in exposure["native"]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_task_summary_and_skill_say_what_was_asked_and_a_skill_is_the_agents_own():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:

        async def turn(name: str, body: dict[str, Any]) -> str:
            thread = await fixture.conversation(await fixture.agent(name))
            sent = (await send(fixture, thread["id"], body)).json()
            return await system_text(
                await fixture.lease({**sent["runs"][0], "thread_id": thread["id"]})
            )

        task = {"name": "task", "argument": "راقب الذهب"}
        assert "start it with the task_start tool" in await turn(
            "Tasker", {"content": "/مهمة راقب الذهب", "command": task}
        )
        assert "is the /summary command" in await turn(
            "Summarizer", {"content": "/ملخص", "command": {"name": "summary"}}
        )
        agent = await fixture.agent("Commander")
        other = await fixture.agent("Bystander")
        thread = await fixture.conversation(agent)

        async def skill(owner: dict[str, Any], name: str, enabled: bool = True) -> str:
            created = await fixture.request(
                "POST",
                "/skills",
                {
                    "agent_id": owner["id"],
                    "payload": {"name": name, "content": "خطوات", "enabled": enabled},
                },
            )
            return created["id"]

        mine = await skill(agent, "موجز الأخبار")
        body = {
            "content": "/موجز الأخبار اليوم",
            "command": {"name": "skill", "skill_id": mine, "argument": "اليوم"},
        }
        sent = await send(fixture, thread["id"], body)
        assert sent.status_code == 202
        part = sent.json()["message"]["rich_content"]["parts"][0]
        assert part["skill_name"] == "موجز الأخبار" and part["skill_id"] == mine
        context = await fixture.lease({**sent.json()["runs"][0], "thread_id": thread["id"]})
        system = await system_text(context)
        # The Agent is told the skill by its catalog id; the owner's name for it stays out.
        assert "the one whose id is legacy-" in system
        assert "موجز الأخبار" not in system.split("<lonora_owner_command>")[1]

        for foreign in (
            await skill(other, "ليست له"),
            await skill(agent, "معطّلة", enabled=False),
            str(uuid4()),
        ):
            refused = await send(
                fixture,
                thread["id"],
                {"content": "/x", "command": {"name": "skill", "skill_id": foreign}},
            )
            assert refused.status_code == 404
            assert refused.json()["code"] == "skill_not_found"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_group_takes_search_but_not_a_task_or_a_skill():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        first = await fixture.agent("First")
        lead = await fixture.agent("Lead")
        group = await fixture.request(
            "POST",
            "/groups/create",
            {"name": "فريق", "member_ids": [first["id"], lead["id"]], "lead_agent_id": lead["id"]},
        )
        fixture.groups.append(group["id"])
        fixture.group_threads.append(group["thread_id"])
        refused = await send(
            fixture,
            group["thread_id"],
            {"content": "/مهمة راقب", "command": {"name": "task", "argument": "راقب"}},
        )
        assert refused.status_code == 409
        assert refused.json()["code"] == "command_unavailable"
        sent = await send(
            fixture, group["thread_id"], {"content": "/بحث أسعار الذهب", "command": SEARCH}
        )
        assert sent.status_code == 202
        assert [run["agent_id"] for run in sent.json()["runs"]] == [lead["id"]]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_command_sent_while_the_reply_is_running_still_says_what_was_asked(
    task_db: Any, monkeypatch: pytest.MonkeyPatch
):
    """The message steers the running Run: the turn reads the same paragraph, after the
    owner's own words."""
    from lonora_adapter_kit.types import ModelReply
    from lonora_agent.executor import execute_run
    from lonora_agent.runtime_notices import is_owner_message, is_runtime_notice
    from lonora_db.messages import send_message
    from lonora_tools.registry import ToolRegistry
    from test_tool_loop_execution import Script, conversation_run, saved_run

    async def no_skill_refresh(*_: Any, **__: Any) -> None:
        return None

    context = await conversation_run(task_db)
    db, owner, _, thread = task_db
    async with db.sessions() as session, session.begin():
        steered = await send_message(
            session,
            owner,
            thread,
            MessageCreate.model_validate(
                {"content": "/search btc etf", "command": {"name": "search", "argument": "btc etf"}}
            ),
        )
        assert steered["run_ids"] == [context.lease.run_id]
    monkeypatch.setattr("lonora_agent.tool_loop.refresh_skill_context", no_skill_refresh)
    model = Script(ModelReply(text="Searched."))
    monkeypatch.setattr("lonora_agent.tool_loop.model_turn", model)
    await execute_run(context, ToolRegistry([]), 120, 8)
    assert (await saved_run(context)).status == "completed"
    first, _ = model.requests[0]
    said = next(i for i, item in enumerate(first) if item.content == "/search btc etf")
    assert is_owner_message(first[said])
    assert is_runtime_notice(first[said + 1])
    assert "is the /search command" in first[said + 1].content
