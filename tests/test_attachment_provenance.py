"""6.10, 14.3.8: only the owner's typed words are the owner's words.

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
    finally:
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
