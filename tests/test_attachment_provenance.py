"""6.10, 14.3.5: only the owner's typed words are the owner's words.

A photo, a text file or a PDF attached to the owner's message reaches the model, but what
it says is not the owner's word: the Run is marked as having read third-party content, so
a setting only the owner's typed message may change is refused in that turn.
"""

import io
import os
from typing import Any
from unittest.mock import patch
from uuid import uuid4

import pytest
from PIL import Image


@pytest.mark.asyncio
async def test_a_photo_on_the_owners_message_is_not_the_owners_word():
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Uses the real migrated PostgreSQL schema.")
    from check_streaming import Fixture
    from lonora_adapter_kit.types import ModelReply, ToolCall
    from lonora_agent.executor import execute_run
    from lonora_contracts.model_routing import ModelSelection
    from lonora_tools.loader import load_tools
    from lonora_tools.provenance import ATTACHMENT_HINT

    picture = io.BytesIO()
    Image.new("RGB", (8, 8), (10, 200, 10)).save(picture, format="PNG")
    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Photo provenance " + uuid4().hex[:6])
        thread = await fixture.conversation(agent)
        upload = await fixture.client.post(
            "/api/artifacts/upload",
            files={"file": ("note.png", picture.getvalue(), "image/png")},
            data={"thread_id": thread["id"]},
        )
        assert upload.status_code == 201, upload.text
        sent = await fixture.request(
            "POST",
            f"/threads/{thread['id']}/messages",
            {
                "content": "شوف الصورة",
                "attachment_ids": [upload.json()["id"]],
                "client_nonce": "photo-" + uuid4().hex,
            },
        )
        run = {"id": sent["run_ids"][0], "agent_id": agent["id"], "thread_id": thread["id"]}
        context = await fixture.lease(run)
        seen: list[str] = []
        turns = [
            ToolCall(id="prefs", name="owner_preferences_update", arguments={"reach_me": "call"})
        ]

        async def model(_: Any, messages: list[Any], *args: Any, **kwargs: Any):
            seen.append("\n".join(str(message.content) for message in messages))
            if turns:
                return ModelReply(tool_calls=[turns.pop(0)]), ModelSelection(
                    provider="openai", model="scripted-photo"
                )
            return ModelReply(text="تم."), ModelSelection(provider="openai", model="scripted-photo")

        with patch("lonora_agent.tool_loop.model_turn", model):
            await execute_run(context, load_tools(), 120, 8)
        assert "owner_preferences_require_owner_message" in seen[-1]
        # The refusal says why: the attachment, and how the owner can ask instead.
        assert ATTACHMENT_HINT in seen[-1]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_refusal_names_the_attachment_only_when_an_attachment_is_why():
    """The owner's typed request with an attachment: the ticket gate, the door,
    broker_connect, reach-me, source trust and model_request say the attachment is why
    and how to ask again. A run that read a web page instead, or a routine wake that
    read an attachment (no owner's words to stand either way), keeps each refusal's own
    text."""
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("Uses the real migrated PostgreSQL schema.")
    from dataclasses import replace
    from decimal import Decimal
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from check_streaming import Fixture
    from lonora_adapters.market import news_feed
    from lonora_contracts.account import Position
    from lonora_core.user_error import ToolRefusal
    from lonora_security.public_http import PublicResponse
    from lonora_tools.memory import PREFERENCES_MESSAGE_REQUIRED
    from lonora_tools.provenance import ATTACHMENT_HINT, mark_external_content
    from test_proactive_wakes import retire, simulation
    from test_supervision import add_messages, owner_says, wake

    # Its tool name is positional only: news_feed_subscribe takes a "name".
    from test_trusted_sources import RSS, call

    async def refusal(context: Any, name: str, **arguments: Any) -> ToolRefusal:
        with pytest.raises(ToolRefusal) as raised:
            await call(context, name, **arguments)
        return raised.value

    async def public(url: str, method: str = "GET", *, maximum_bytes: int = 0) -> Any:
        return PublicResponse(200, {"content-type": "application/rss+xml"}, RSS)

    trust_text = (
        "Nothing was trusted. Only the owner trusts a source: ask him to name it in chat "
        "(its domain, GitHub owner/repository or server name), then call this again before "
        "reading anything else in that run."
    )
    model_text = "Nothing changed. Only the owner assigns a model: ask him to name it in chat."
    fixture = await Fixture().open()
    connection = ""
    try:
        manual = Position(
            id="owner-ticket-" + uuid4().hex[:6],
            symbol="XAUUSD",
            side="buy",
            volume=Decimal("0.2"),
            open_price=Decimal(100),
            stop_loss=Decimal(90),
        )
        connection = await simulation(fixture, [manual])
        agent = await fixture.agent("Attachment hint", supervised=True)
        cases = (
            ("user", "owner_attachment", ATTACHMENT_HINT),
            ("user", "web_fetch", None),
            ("routine", "owner_attachment", None),
        )
        for trigger, source, hint in cases:
            thread = await fixture.conversation(agent)
            if trigger == "user":
                context = await owner_says(fixture, agent, thread, "close the owner's ticket")
            else:
                # The owner's typed message is in the thread, but a routine wake does not
                # answer it: an attachment is not why his words do not stand.
                await add_messages(fixture, thread["id"], [("user", None, "close my ticket")])
                context = await wake(fixture, agent, thread)
            async with fixture.runtime.db.sessions() as session, session.begin():
                await mark_external_content(session, context.lease.run_id, source)
            suffix = " " + hint if hint else ""
            ticket = await refusal(
                context,
                "trade_execute",
                account_id=connection,
                symbol="XAUUSD",
                action="close_position",
                position_id=manual.id,
            )
            assert ticket.code == "ticket_not_owned"
            assert ticket.details.get("hint") == hint, ticket.details
            # A close-all reaches the door, which refuses the owner's ticket on its own.
            batch = await call(context, "trade_close_positions", account_id=connection)
            assert [item["code"] for item in batch["results"]] == ["ticket_not_owned"], batch
            assert batch["results"][0]["details"].get("hint") == hint, batch
            connect = await refusal(
                context, "broker_connect", login="70000001", server="Fixture-MT5Trial"
            )
            assert connect.code == "broker_connect_needs_owner_message"
            assert connect.details["hint"] == (
                hint or "Connect an account only when the owner asks in chat."
            )
            manage = await refusal(
                context, "broker_manage", account_id=connection, action="disable"
            )
            assert manage.code == "broker_manage_needs_owner_message"
            assert manage.details["hint"] == (
                hint or "Change a broker connection only when the owner asks in chat."
            )
            # Reach-me, source trust and model_request keep their own guidance; the hint
            # follows it.
            reach = await call(context, "owner_preferences_update", reach_me="call")
            assert reach["code"] == "owner_preferences_require_owner_message", reach
            assert reach["recovery"] == str(PREFERENCES_MESSAGE_REQUIRED["recovery"]) + suffix
            site = "hint-" + uuid4().hex[:8] + ".example"
            with patch.object(news_feed, "public_get", public):
                feed = await call(
                    context, "news_feed_subscribe", url="https://" + site + "/rss", name="Hint"
                )
            assert feed["code"] == "trust_requires_owner_message", feed
            assert feed["recovery"] == trust_text + suffix
            # Any connected catalog model: the gate under test comes after both checks.
            with patch("lonora_tools.models.catalog_has", AsyncMock(return_value=True)):
                model = await call(
                    replace(context, router=SimpleNamespace()),
                    "model_request",
                    model={"provider": "openai", "model": "hint-model"},
                )
            assert model["code"] == "model_assignment_requires_owner_message", model
            assert model["recovery"] == model_text + suffix
    finally:
        await retire(fixture, connection)
        await fixture.close()


@pytest.mark.asyncio
async def test_a_steering_attachment_is_read_in_its_own_conversation(monkeypatch: Any):
    """A message that steers a background run may come from another conversation: its
    attachment is looked up there, so it still marks the run (6.10)."""
    from types import SimpleNamespace
    from unittest.mock import AsyncMock

    from lonora_agent import steering

    row = SimpleNamespace(
        id="m1",
        thread_id="owner-thread",
        seq=7,
        attachment_ids=["a1"],
        content="look",
        rich_content=None,
        role="user",
    )
    looked_up: list[tuple[str, int]] = []

    async def third_party(session: Any, owner_id: str, thread_id: str, seq: int) -> bool:
        looked_up.append((thread_id, seq))
        return True

    marked = AsyncMock()
    monkeypatch.setattr(steering, "consume_steering", AsyncMock(return_value=[row]))
    monkeypatch.setattr(steering, "attachment_context", AsyncMock(return_value=("note", [])))
    monkeypatch.setattr(steering, "third_party_attachment", third_party)
    monkeypatch.setattr(steering, "mark_external_content", marked)

    def nothing(*args: Any, **kwargs: Any) -> None:
        return None

    monkeypatch.setattr(steering, "merge_answer", nothing)
    monkeypatch.setattr(steering, "checkpoint", AsyncMock())
    monkeypatch.setattr(steering, "reset_stop_gate", nothing)
    monkeypatch.setattr(steering, "reset_guardrails", nothing)

    class Session:
        async def __aenter__(self) -> "Session":
            return self

        async def __aexit__(self, *args: Any) -> None:
            return None

        def begin(self) -> "Session":
            return self

    context = SimpleNamespace(
        db=SimpleNamespace(sessions=Session),
        owner_id="owner",
        thread_id="work-thread",
        artifact_root=None,
        lease=SimpleNamespace(run_id="run-1"),
    )
    await steering.merge_steering(context, {}, [])  # type: ignore[arg-type]
    assert looked_up == [("owner-thread", 7)]
    marked.assert_awaited_once()
