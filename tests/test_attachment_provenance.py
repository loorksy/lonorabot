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
