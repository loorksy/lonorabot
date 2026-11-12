"""Conversation conveniences (UI phase 3, WP-D): reactions, the suggested reply, per-chat
web search, edit and resend, and guests by @mention in a direct chat.

The pure cases run everywhere. The PostgreSQL cases (LONORA_DATABASE_URL) go through the
owner API and the runtime on the migrated schema.
"""

import json
import os
import re
from pathlib import Path
from types import SimpleNamespace
from typing import Any, cast
from unittest.mock import AsyncMock
from urllib.parse import quote
from uuid import uuid4

import pytest
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent import model_runtime
from lonora_agent.suggested_reply import split_suggested_reply, suggestion_stream_prefix
from lonora_contracts.domain import MessageCreate, ThreadOptions
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_contracts.reactions import REACTION_EMOJIS
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from pydantic import ValidationError

ROOT = Path(__file__).resolve().parents[1]

# --- Pure ---------------------------------------------------------------------------


def test_reaction_emojis_are_the_reference_six_in_python_and_typescript():
    assert REACTION_EMOJIS == ("👍", "❤️", "😂", "😮", "😢", "🙏")
    source = (ROOT / "packages/contracts/src/domain.ts").read_text()
    match = re.search(r"REACTION_EMOJIS = (\[[^\]]*\]) as const", source)
    assert match is not None
    assert tuple(json.loads(match.group(1))) == REACTION_EMOJIS


def test_contracts_carry_the_new_fields():
    assert MessageCreate(content="x", edited_from="m1").edited_from == "m1"
    assert ThreadOptions().web_search is False
    with pytest.raises(ValidationError):
        ThreadOptions.model_validate({"web_search": True, "other": 1})


def test_suggested_reply_is_split_from_a_trailing_tag_only():
    assert split_suggested_reply("Gold rose.\n<suggested_reply>Why?</suggested_reply>") == (
        "Gold rose.\n",
        "Why?",
    )
    # No tag: unchanged.
    assert split_suggested_reply("Plain answer.") == ("Plain answer.", None)
    # Longer than 60 characters after trimming: stripped, no suggestion.
    long = "x" * 61
    assert split_suggested_reply(f"A.<suggested_reply>{long}</suggested_reply>") == ("A.", None)
    assert split_suggested_reply(f"A.<suggested_reply>  {'y' * 60} </suggested_reply>") == (
        "A.",
        "y" * 60,
    )
    # Not trailing: stripped but not kept.
    assert split_suggested_reply("A <suggested_reply>Hi</suggested_reply> B") == ("A  B", None)
    # An unclosed tag at the end is still never shown.
    assert split_suggested_reply("A.\n<suggested_reply>شكرًا") == ("A.\n", "شكرًا")
    assert split_suggested_reply("A.<suggested_reply> </suggested_reply>") == ("A.", None)


def test_stream_prefix_withholds_a_tag_and_its_split_opening():
    assert suggestion_stream_prefix("Hello world") == "Hello world"
    assert suggestion_stream_prefix("Hello <sugg") == "Hello "
    assert suggestion_stream_prefix("Hello <") == "Hello "
    assert suggestion_stream_prefix("Hello <suggested_reply>Th") == "Hello "
    assert suggestion_stream_prefix("a < b and more") == "a < b and more"


def scripted_context(chunks: list[str], reply: ModelReply) -> ToolContext:
    async def complete(_capability: Any, _messages: Any, _tools: Any, **kwargs: Any):
        selection = ModelSelection(provider="openai", model="scripted")
        await kwargs["on_attempt"](selection)
        for chunk in chunks:
            await kwargs["on_delta"](chunk)
        return reply, selection

    return cast(
        ToolContext,
        SimpleNamespace(
            db=None,
            owner_id="owner",
            agent_id="agent",
            thread_id="thread",
            lease=SimpleNamespace(run_id="run"),
            router=SimpleNamespace(complete=complete),
        ),
    )


async def scripted_turn(
    monkeypatch: pytest.MonkeyPatch, chunks: list[str], reply: ModelReply | None = None
) -> tuple[ModelReply, str]:
    monkeypatch.setattr("lonora_agent.public_stream.monotonic", lambda: 0.0)
    published = AsyncMock()

    async def images(
        _context: Any, messages: list[ModelMessage]
    ) -> tuple[list[ModelMessage], dict[str, Any]]:
        return messages, {}

    monkeypatch.setattr(model_runtime, "refresh_routing_context", AsyncMock())
    monkeypatch.setattr(model_runtime, "prepare_image_observations", images)
    monkeypatch.setattr(model_runtime, "save_usage", AsyncMock())
    monkeypatch.setattr(model_runtime, "progress", published)
    context = scripted_context(chunks, reply or ModelReply(text="".join(chunks)))
    result, _ = await model_runtime.model_turn(
        context, [ModelMessage(role="user", content="How is gold?")], [], Capability.CONVERSATION
    )
    streamed = "".join(
        item.args[2]["text"] for item in published.await_args_list if item.args[1] == "run.delta"
    )
    return result, streamed


@pytest.mark.asyncio
async def test_a_tag_split_across_stream_deltas_never_streams_and_is_kept_aside(
    monkeypatch: pytest.MonkeyPatch,
):
    answer = "Gold rose half a percent this morning after the inflation data came out. "
    chunks = [
        answer[:30],
        answer[30:],
        "It may extend into the close.\n<sugg",
        "ested_re",
        "ply>Show me the ",
        "chart</suggest",
        "ed_reply>",
    ]
    reply, streamed = await scripted_turn(monkeypatch, chunks)
    assert "<" not in streamed and "suggest" not in streamed and "chart" not in streamed
    # Whitespace before the tag that already streamed stays, so the stream is a prefix.
    assert reply.text.rstrip() == answer + "It may extend into the close."
    assert streamed == reply.text
    assert reply.provider_metadata["suggested_reply"] == "Show me the chart"


@pytest.mark.asyncio
async def test_whitespace_already_streamed_before_the_tag_stays_a_prefix(
    monkeypatch: pytest.MonkeyPatch,
):
    chunks = ["The market is calm today, nothing moved much.\n\n", "<suggested_reply>OK</sug"]
    chunks.append("gested_reply>")
    reply, streamed = await scripted_turn(monkeypatch, chunks)
    assert reply.text.startswith(streamed) and "<" not in reply.text
    assert reply.text.strip() == "The market is calm today, nothing moved much."
    assert reply.provider_metadata["suggested_reply"] == "OK"


@pytest.mark.asyncio
async def test_no_suggestion_with_tool_calls_or_a_generated_interface(
    monkeypatch: pytest.MonkeyPatch,
):
    text = "Checking now. <suggested_reply>Thanks</suggested_reply>"
    reply, streamed = await scripted_turn(
        monkeypatch,
        [text],
        ModelReply(text=text, tool_calls=[ToolCall(id="c1", name="memory_read", arguments={})]),
    )
    assert "suggested" not in streamed and "suggested" not in reply.text
    assert reply.provider_metadata["suggested_reply"] is None
    visual = (
        "Here it is.\n```lonora-ui\n"
        + "\n".join(
            json.dumps(line)
            for line in (
                {"v": 2, "kind": "receipt", "title": "Hello", "icon": "info"},
                {"type": "Text", "text": "Hello"},
                {"why": "A short note.", "fallback": "Hello."},
            )
        )
        + "\n```\n<suggested_reply>More</suggested_reply>"
    )
    from lonora_agent.genui_compile import AgentScope
    from lonora_agent.visual_response import VisualReplyProjector

    async def scope(self: VisualReplyProjector) -> AgentScope:
        return AgentScope(agent_id="agent")  # the scripted turn has no database

    monkeypatch.setattr(VisualReplyProjector, "agent_scope", scope)
    reply, _ = await scripted_turn(monkeypatch, [visual])
    assert reply.rich_content is not None
    assert "suggested" not in reply.text
    assert reply.provider_metadata["suggested_reply"] is None


@pytest.mark.asyncio
async def test_a_suggestion_needing_redaction_is_dropped(monkeypatch: pytest.MonkeyPatch):
    """M9: the suggested reply passes the same privacy boundary as the answer."""
    private = "3f2b8c1e-9a4d-4e7b-8c21-5d6f7a8b9c0d"
    text = f"Gold is steady. <suggested_reply>Open {private}</suggested_reply>"
    reply, streamed = await scripted_turn(monkeypatch, [text])
    assert private not in streamed and private not in reply.text
    assert reply.provider_metadata["suggested_reply"] is None
    assert reply.provider_metadata["privacy_redacted"] is True
    # A clean suggestion is untouched.
    reply, _ = await scripted_turn(
        monkeypatch, ["Gold is steady. <suggested_reply>Show the chart</suggested_reply>"]
    )
    assert reply.provider_metadata["suggested_reply"] == "Show the chart"


def test_message_react_is_registered_with_its_policy():
    registry = load_tools()
    tool = registry.tools["message_react"]
    assert not tool.financial and not tool.read_only
    assert "genuinely fitting" in tool.description and "Never react to every message" in (
        tool.description
    )
    manifest = json.loads(
        (ROOT / "packages/agent-runtime/resources/system/manifest.json").read_text()
    )
    assert manifest["tool_policies"]["message_react"] == "collaboration"


# --- PostgreSQL: the owner API and the runtime on the migrated schema ------------------


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The conversation convenience cases use the real migrated PostgreSQL schema.")


async def agent_reply(
    fixture: Any, thread_id: str, agent_id: str, text: str, role: str = "assistant"
):
    from test_thread_preferences import agent_reply as reply

    if role == "assistant":
        return await reply(fixture, thread_id, agent_id, text)
    from lonora_db.schema import MessageRow, ThreadRow

    async with fixture.runtime.db.sessions() as session, session.begin():
        thread = await session.get(ThreadRow, thread_id, with_for_update=True)
        assert thread is not None
        message = MessageRow(
            thread_id=thread_id, agent_id=None, seq=thread.next_seq, role=role, content=text
        )
        thread.next_seq += 1
        session.add(message)
        await session.flush()
        return message.id


async def send(fixture: Any, thread_id: str, body: dict[str, Any]) -> Any:
    return await fixture.client.post(
        f"/api/threads/{thread_id}/messages",
        json={"client_nonce": "wpd-" + uuid4().hex, **body},
    )


async def page(fixture: Any, thread_id: str) -> list[dict[str, Any]]:
    response = await fixture.client.get(f"/api/threads/{thread_id}/messages")
    assert response.is_success
    return response.json()


@pytest.mark.asyncio
async def test_owner_and_agent_reactions_replace_remove_and_project():
    database()
    from check_streaming import Fixture
    from lonora_db.reactions import agent_reaction
    from test_thread_preferences import events_of

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Reactor")
        thread = await fixture.conversation(agent)
        sent = (await send(fixture, thread["id"], {"content": "اشترِ لي تقريرًا"})).json()
        message_id = sent["message"]["id"]
        assert sent["message"]["reactions"] == [] and sent["message"]["superseded_by"] is None
        base = f"/api/threads/{thread['id']}/messages/{message_id}/reactions"
        first = await fixture.client.put(base + "/" + quote("👍"))
        assert first.status_code == 200
        assert [r["emoji"] for r in first.json()["reactions"]] == ["👍"]
        # The owner's one reaction is replaced, never added beside the first.
        second = (await fixture.client.put(base + "/" + quote("❤"))).json()
        assert second["message_id"] == message_id
        assert [(r["reactor"], r["emoji"]) for r in second["reactions"]] == [("owner", "❤️")]
        refused = await fixture.client.put(base + "/" + quote("🔥"))
        assert refused.status_code == 422 and refused.json()["code"] == "reaction_not_allowed"
        async with fixture.runtime.db.sessions() as session, session.begin():
            await agent_reaction(
                session, fixture.owner, agent["id"], thread["id"], message_id, "🙏"
            )
        items = await page(fixture, thread["id"])
        reactions = next(item for item in items if item["id"] == message_id)["reactions"]
        assert [(r["reactor"], r["emoji"]) for r in reactions] == [
            ("owner", "❤️"),
            (agent["id"], "🙏"),
        ]
        removed = (await fixture.client.delete(base)).json()
        assert [r["reactor"] for r in removed["reactions"]] == [agent["id"]]
        events = await events_of(fixture, "message.reaction_updated", thread["id"])
        assert len(events) == 4
        assert events[-1].payload == {
            "thread_id": thread["id"],
            "message_id": message_id,
            "reactions": removed["reactions"],
        }
        # Call and system notices take no reaction; another thread's message is not found.
        notice = await agent_reply(fixture, thread["id"], agent["id"], "مكالمة فائتة", "system")
        response = await fixture.client.put(
            f"/api/threads/{thread['id']}/messages/{notice}/reactions/" + quote("👍")
        )
        assert response.status_code == 404 and response.json()["code"] == "message_not_found"
        # «مسح» hides the message: it can no longer be reacted to.
        await fixture.request("POST", f"/threads/{thread['id']}/clear")
        hidden = await fixture.client.put(base + "/" + quote("👍"))
        assert hidden.status_code == 404 and hidden.json()["code"] == "message_not_found"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_web_search_option_is_persisted_projected_and_read_by_the_agent(
    monkeypatch: pytest.MonkeyPatch,
):
    database()
    from check_streaming import Fixture
    from lonora_agent.context.builder import build_context
    from lonora_agent.tool_exposure import ensure_exposure
    from test_thread_preferences import events_of

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Researcher")
        thread = await fixture.conversation(agent)
        assert thread["options"] == {"web_search": False}
        updated = await fixture.request(
            "PUT", f"/threads/{thread['id']}/options", {"web_search": True}
        )
        assert updated["id"] == thread["id"] and updated["options"] == {"web_search": True}
        assert (await fixture.request("GET", f"/threads/{thread['id']}"))["options"] == {
            "web_search": True
        }
        listed = cast(list[dict[str, Any]], await fixture.request("GET", "/threads"))
        assert next(t for t in listed if t["id"] == thread["id"])["options"]["web_search"]
        events = await events_of(fixture, "thread.updated", thread["id"])
        assert events[-1].payload == {"thread_id": thread["id"], "options": {"web_search": True}}
        bad = await fixture.client.put(f"/api/threads/{thread['id']}/options", json={"x": 1})
        assert bad.status_code == 422

        sent = (await send(fixture, thread["id"], {"content": "ما آخر أخبار الذهب؟"})).json()
        context = await fixture.lease({**sent["runs"][0], "thread_id": thread["id"]})
        messages = await build_context(context)
        system = "\n".join(m.content for m in messages if m.role == "system")
        assert "switched on web search for this chat" in system
        assert "<suggested_reply>" in system
        # A trading identity's profiles leave web_search out; the chat option preselects it.

        def trading_profiles(*_a: object, **_k: object) -> list[str]:
            return ["core", "market"]

        monkeypatch.setattr("lonora_agent.tool_exposure.run_profiles", trading_profiles)
        registry = load_tools()
        monkeypatch.setattr(registry, "availability", AsyncMock(return_value={}))
        exposure = await ensure_exposure(
            context, registry, {}, [], [], scope="full", task_run=False
        )
        assert "web_search" in exposure["native"]

        await fixture.request("PUT", f"/threads/{thread['id']}/options", {"web_search": False})
        exposure = await ensure_exposure(
            context, registry, {}, [], [], scope="full", task_run=False
        )
        assert "web_search" not in exposure["native"]
        messages = await build_context(context)
        system = "\n".join(m.content for m in messages if m.role == "system")
        assert "switched on web search for this chat" not in system
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_edit_and_resend_cancels_the_original_run_and_links_both_messages():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import ArtifactRow, RunRow

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Editor")
        thread = await fixture.conversation(agent)
        original = (await send(fixture, thread["id"], {"content": "حلّل اليورو"})).json()
        original_id = original["message"]["id"]
        run_id = original["run_ids"][0]
        edited = await send(
            fixture, thread["id"], {"content": "حلّل الذهب", "edited_from": original_id}
        )
        assert edited.status_code == 202, edited.text
        body = edited.json()
        assert body["message"]["edited_from"] == original_id
        assert body["run_ids"] and body["run_ids"][0] != run_id
        async with fixture.runtime.db.sessions() as session:
            run = await session.get(RunRow, run_id)
            assert run is not None and run.status == "cancelled"
        items = await page(fixture, thread["id"])
        by_id = {item["id"]: item for item in items}
        # Nothing is deleted: the original stays, superseded by the edit.
        assert by_id[original_id]["superseded_by"] == body["message"]["id"]
        assert by_id[body["message"]["id"]]["superseded_by"] is None
        assert by_id[body["message"]["id"]]["edited_from"] == original_id

        again = await send(fixture, thread["id"], {"content": "x", "edited_from": original_id})
        assert again.status_code == 409 and again.json()["code"] == "message_already_edited"
        answer = await agent_reply(fixture, thread["id"], agent["id"], "جواب")
        refused = await send(fixture, thread["id"], {"content": "x", "edited_from": answer})
        assert refused.status_code == 409 and refused.json()["code"] == "message_not_editable"
        missing = await send(fixture, thread["id"], {"content": "x", "edited_from": str(uuid4())})
        assert missing.status_code == 404 and missing.json()["code"] == "message_not_found"
        async with fixture.runtime.db.sessions() as session, session.begin():
            artifact = ArtifactRow(
                owner_id=fixture.owner, payload={"name": "a.txt"}, thread_id=thread["id"]
            )
            session.add(artifact)
            await session.flush()
            artifact_id = artifact.id
        with_file = (
            await send(fixture, thread["id"], {"content": "ملف", "attachment_ids": [artifact_id]})
        ).json()
        refused = await send(
            fixture, thread["id"], {"content": "x", "edited_from": with_file["message"]["id"]}
        )
        assert refused.status_code == 409 and refused.json()["code"] == "message_not_editable"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_an_edited_message_leaves_history_steering_and_clients_marked_replaced():
    """M7: every later run reads only the replacement; a running reply never consumes the
    replaced instruction; clients learn the original is superseded; voice notes are not
    editable."""
    database()
    from check_streaming import Fixture
    from lonora_agent.context.history import history_context
    from lonora_db.schema import EventRow, MessageRow, RunRow, SteeringRow
    from sqlalchemy import select

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Editor")
        thread = await fixture.conversation(agent)
        first = (await send(fixture, thread["id"], {"content": "حلّل اليورو"})).json()
        running = first["run_ids"][0]
        await fixture.lease({"id": running, **await fixture.request("GET", f"/runs/{running}")})
        # Sent while the reply runs: it steers that run.
        steered = (await send(fixture, thread["id"], {"content": "اشترِ 1 لوت"})).json()
        steered_id = steered["message"]["id"]
        async with fixture.runtime.db.sessions() as session:
            assert await session.scalar(
                select(SteeringRow.id).where(SteeringRow.message_id == steered_id)
            )
        edited = await send(
            fixture, thread["id"], {"content": "حلّل فقط", "edited_from": steered_id}
        )
        assert edited.status_code == 202, edited.text
        new_id = edited.json()["message"]["id"]
        async with fixture.runtime.db.sessions() as session:
            # Withdrawn from the running reply's queue.
            assert (
                await session.scalar(
                    select(SteeringRow.id).where(SteeringRow.message_id == steered_id)
                )
                is None
            )
            # Clients see the original replaced, live.
            update = await session.scalar(
                select(EventRow)
                .where(EventRow.kind == "message.updated", EventRow.thread_id == thread["id"])
                .order_by(EventRow.cursor.desc())
            )
            assert update is not None
            assert update.payload["id"] == steered_id
            assert update.payload["superseded_by"] == new_id
            # Every later run reads only the replacement.
            new_seq = await session.scalar(select(MessageRow.seq).where(MessageRow.id == new_id))
            assert new_seq is not None
            history = await history_context(session, thread["id"], new_seq)
            texts = [message.content for message in history]
            assert any("حلّل فقط" in text for text in texts)
            assert not any("اشترِ 1 لوت" in text for text in texts)
            # A voice note has no text to edit.
            voice = MessageRow(
                thread_id=thread["id"],
                seq=new_seq + 100,
                role="user",
                content="",
                rich_content={"version": 1, "parts": [{"type": "voice", "artifact_id": "a"}]},
            )
        async with fixture.runtime.db.sessions() as session, session.begin():
            session.add(voice)
            await session.flush()
            voice_id = voice.id
            run = await session.get(RunRow, running)
            assert run is not None
        refused = await send(fixture, thread["id"], {"content": "x", "edited_from": voice_id})
        assert refused.status_code == 409 and refused.json()["code"] == "message_not_editable"
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_suggested_reply_is_stored_on_a_conversational_answer_only():
    database()
    from check_streaming import Fixture
    from lonora_db.runs import complete_run
    from lonora_db.schema import TradeApprovalRow
    from test_thread_preferences import events_of

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Suggester")
        thread = await fixture.conversation(agent)
        sent = (await send(fixture, thread["id"], {"content": "كيف الذهب؟"})).json()
        context = await fixture.lease({**sent["runs"][0], "thread_id": thread["id"]})
        async with fixture.runtime.db.sessions() as session, session.begin():
            assert await complete_run(
                session, context.lease, "الذهب مستقر.", {"suggested_reply": " أرني الشارت "}
            )
        items = await page(fixture, thread["id"])
        assert items[-1]["role"] == "assistant" and items[-1]["suggested_reply"] == "أرني الشارت"
        created = await events_of(fixture, "message.created", thread["id"])
        assert created[-1].payload["suggested_reply"] == "أرني الشارت"

        # A run that raised a card in this turn keeps no suggestion.
        sent = (await send(fixture, thread["id"], {"content": "اشترِ ذهبًا"})).json()
        run = sent["runs"][0]
        context = await fixture.lease({**run, "thread_id": thread["id"]})
        async with fixture.runtime.db.sessions() as session, session.begin():
            session.add(
                TradeApprovalRow(
                    id=str(uuid4()),
                    owner_id=fixture.owner,
                    run_id=run["id"],
                    thread_id=thread["id"],
                    agent_id=agent["id"],
                    call_id="c1",
                    requests=[],
                    status="rejected",
                )
            )
        async with fixture.runtime.db.sessions() as session, session.begin():
            assert await complete_run(
                session, context.lease, "لم يُنفَّذ شيء.", {"suggested_reply": "حسنًا"}
            )
        assert (await page(fixture, thread["id"]))[-1]["suggested_reply"] is None
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_mention_in_a_direct_chat_invites_guests_into_one_session():
    database()
    from check_streaming import Fixture
    from lonora_agent.collaboration.outcome_return import return_outcome
    from lonora_db.collaboration import current_session
    from lonora_db.schema import RunRow

    fixture = await Fixture().open()
    try:
        host = await fixture.agent("Host")
        guests = [await fixture.agent(f"Guest {index}") for index in range(3)]
        thread = await fixture.conversation(host)
        # Mandate P1 / 3.2.5: no cap on the agents the owner names. A second host's chat
        # takes all three guests in one message, in one session.
        other_host = await fixture.agent("Other host")
        other_thread = await fixture.conversation(other_host)
        everyone = await send(
            fixture,
            other_thread["id"],
            {"content": "رأيكم؟", "mention_agent_ids": [g["id"] for g in guests]},
        )
        assert everyone.status_code == 202, everyone.text
        async with fixture.runtime.db.sessions() as session:
            joined = await current_session(session, fixture.owner, other_thread["id"])
            assert joined is not None
            assert len(joined.state["participants"]) == 3

        first = await send(
            fixture, thread["id"], {"content": "رأيك؟", "mention_agent_ids": [guests[0]["id"]]}
        )
        assert first.status_code == 202, first.text
        async with fixture.runtime.db.sessions() as session:
            row = await current_session(session, fixture.owner, thread["id"])
            assert row is not None
            session_id = row.id
            assert [p["agent_id"] for p in row.state["participants"]] == [guests[0]["id"]]
        # A later mention joins the chat's open session instead of starting another.
        await fixture.request("PATCH", f"/agents/{guests[2]['id']}", {"paused": True})
        second = await send(
            fixture,
            thread["id"],
            {
                "content": "وأنت؟",
                "mention_agent_ids": [guests[1]["id"], guests[2]["id"], host["id"]],
            },
        )
        assert second.status_code == 202, second.text
        assert second.json()["message"]["mentions"]["session_id"] == session_id
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await current_session(session, fixture.owner, thread["id"])
            assert row is not None and row.id == session_id
            # The paused guest is not invited; the chat's own agent is never its own guest.
            assert [p["agent_id"] for p in row.state["participants"]] == [
                guests[0]["id"],
                guests[1]["id"],
            ]
            guest_run_id = row.state["participants"][1]["run_ids"][0]
            guest_run = await session.get(RunRow, guest_run_id)
            assert guest_run is not None
            guest_run.status, guest_run.result = "completed", "رأيي: الذهب صاعد"
        await return_outcome(fixture.runtime.db, guest_run_id)
        items = await page(fixture, thread["id"])
        answer = [item for item in items if item["agent_id"] == guests[1]["id"]]
        # The guest answers in the host's chat under its own agent id.
        assert len(answer) == 1 and "رأيي: الذهب صاعد" in answer[0]["content"]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_message_react_defaults_to_the_owner_message_being_answered():
    """The model never sees message ids: without one, the reaction lands on the owner's
    message this turn answers."""
    database()
    from check_streaming import Fixture
    from lonora_tools.message import react

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Reactor")
        thread = await fixture.conversation(agent)
        sent = (await send(fixture, thread["id"], {"content": "شكرًا"})).json()
        context = await fixture.lease({**sent["runs"][0], "thread_id": thread["id"]})
        await react(context, {"emoji": "👍"})
        items = await page(fixture, thread["id"])
        owner = next(item for item in items if item["id"] == sent["message"]["id"])
        assert [(row["emoji"], row["reactor"]) for row in owner["reactions"]] == [
            ("👍", agent["id"])
        ]
    finally:
        await fixture.close()
