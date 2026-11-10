"""Voice notes and call log bubbles (UI phase 3, WP-E; owner decisions Q24, Q34).

The pure cases run everywhere. The PostgreSQL cases (LONORA_DATABASE_URL) go through the
owner API on the migrated schema with the transcription provider faked (no network):
a voice note is stored pending with no Run, the Gateway step transcribes it, emits
``message.updated`` and only then admits the Agent's Run; a failed transcript admits the
Run with the server's note. Calls are logged once as system messages in the Agent's
conversation and never start a Run.
"""

import os
import time
from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from lonora_contracts.domain import MessageCreate, new_id, utcnow
from lonora_contracts.visual_response import RichContent
from lonora_core.message_preview import (
    VOICE_NOTE_FAILED_TEXT,
    VOICE_NOTE_PENDING_TEXT,
    message_kind,
    model_content,
)
from lonora_core.user_error import LonoraError
from lonora_db.rich_response import validated_rich_content
from pydantic import ValidationError

ARTIFACT = "11111111-2222-4333-8444-555555555555"
PEAKS = [index * 2 for index in range(44)]
VOICE_PART = {
    "type": "voice",
    "artifact_id": ARTIFACT,
    "duration": 7.5,
    "peaks": PEAKS,
    "transcript_status": "pending",
}
CALL_PART = {"type": "call", "direction": "outgoing", "duration_seconds": 42, "missed": False}

# --- Pure ---------------------------------------------------------------------------


def test_rich_content_carries_voice_and_call_parts():
    for part in [VOICE_PART, CALL_PART]:
        parsed = RichContent.model_validate({"version": 1, "parts": [part]})
        assert parsed.model_dump(mode="json")["parts"] == [part]
    bad = [
        {**VOICE_PART, "peaks": PEAKS[:-1]},
        {**VOICE_PART, "peaks": [*PEAKS[:-1], 101]},
        {**VOICE_PART, "peaks": [*PEAKS[:-1], -1]},
        {**VOICE_PART, "duration": 0},
        {**VOICE_PART, "duration": 120.5},
        {**VOICE_PART, "duration": float("nan")},
        {**VOICE_PART, "artifact_id": "../etc/passwd"},
        {**VOICE_PART, "transcript_status": "unknown"},
        {**VOICE_PART, "src": "data:audio/webm;base64,AAAA"},
        {**CALL_PART, "direction": "sideways"},
        {**CALL_PART, "duration_seconds": -1},
        {**CALL_PART, "label": "x"},
    ]
    for part in bad:
        with pytest.raises(ValidationError):
            RichContent.model_validate({"version": 1, "parts": [part]})


def test_an_agent_reply_can_never_publish_a_server_written_part():
    text = {"type": "text", "text": "سمعتك"}
    assert validated_rich_content({"version": 1, "parts": [text]}) is not None
    for part in [VOICE_PART, CALL_PART]:
        assert validated_rich_content({"version": 1, "parts": [text, part]}) is None


def test_the_agent_projector_builds_only_text_and_ui_parts():
    from lonora_agent.visual_response import VisualProjection

    projection = VisualProjection()
    projection.prose("hello")
    projection.saw_visual = True
    rich = projection.rich_until()
    assert rich and {part["type"] for part in rich["parts"]} == {"text"}


def test_message_create_needs_content_unless_it_is_a_voice_note():
    voice = {"artifact_id": ARTIFACT, "duration": 3, "peaks": PEAKS}
    with pytest.raises(ValidationError):
        MessageCreate.model_validate({})
    with pytest.raises(ValidationError):
        MessageCreate.model_validate({"content": ""})
    assert MessageCreate.model_validate({"voice": voice}).content == ""
    for extra in [
        {"content": "caption"},
        {"attachment_ids": [ARTIFACT]},
        {"mention_all": True},
        {"input_answer": {"run_id": "r", "question_id": "q", "choice_id": "c"}},
    ]:
        with pytest.raises(ValidationError):
            MessageCreate.model_validate({"voice": voice, **extra})
    for wrong in [{"peaks": PEAKS[:43]}, {"duration": 121}, {"duration": 0}]:
        with pytest.raises(ValidationError):
            MessageCreate.model_validate({"voice": {**voice, **wrong}})


def test_kind_and_model_content_of_a_voice_note():
    pending: dict[str, Any] = {"version": 1, "parts": [VOICE_PART]}
    failed: dict[str, Any] = {
        "version": 1,
        "parts": [{**VOICE_PART, "transcript_status": "failed"}],
    }
    assert message_kind(pending, []) == "voice"
    assert model_content("", pending) == VOICE_NOTE_PENDING_TEXT
    assert model_content("", failed) == VOICE_NOTE_FAILED_TEXT
    assert model_content("مرحبا", pending) == "مرحبا"
    assert model_content("", None) == ""


# --- PostgreSQL ----------------------------------------------------------------------


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The voice note cases use the real migrated PostgreSQL schema.")


class FakeSpeech:
    calls: list[dict[str, Any]] = []
    failing_models: set[str] = set()
    transcript = "اشترِ الذهب عند الدعم"

    def __init__(self, api_key: str):
        assert api_key == "sk-fixture"

    async def transcribe(
        self,
        audio: bytes,
        model: str,
        *,
        media_type: str = "audio/wav",
        language: str | None = None,
    ) -> str:
        FakeSpeech.calls.append(
            {"audio": audio, "model": model, "media_type": media_type, "language": language}
        )
        if model in FakeSpeech.failing_models:
            raise LonoraError("voice_transcription_failed", 502)
        return FakeSpeech.transcript


class Credentials:
    def __init__(self, configured: bool = True):
        self.configured = configured

    async def resolve(self, provider: str) -> str:
        assert provider == "openai"
        if not self.configured:
            raise LonoraError("model_not_configured", 409)
        return "sk-fixture"


async def upload(fixture: Any, thread_id: str, media_type: str = "audio/webm;codecs=opus") -> str:
    response = await fixture.client.post(
        "/api/artifacts/upload",
        files={"file": ("note.webm", b"OggS-fixture-audio", media_type)},
        data={"thread_id": thread_id},
    )
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def send_voice(fixture: Any, thread_id: str, artifact_id: str, nonce: str) -> Any:
    return await fixture.client.post(
        f"/api/threads/{thread_id}/messages",
        json={
            "client_nonce": nonce,
            "voice": {"artifact_id": artifact_id, "duration": 4.2, "peaks": PEAKS},
        },
    )


async def events_of(fixture: Any, kind: str, thread_id: str) -> list[Any]:
    from lonora_db.schema import EventRow
    from sqlalchemy import select

    async with fixture.runtime.db.sessions() as session:
        return list(
            await session.scalars(
                select(EventRow)
                .where(
                    EventRow.owner_id == fixture.owner,
                    EventRow.kind == kind,
                    EventRow.thread_id == thread_id,
                )
                .order_by(EventRow.cursor)
            )
        )


async def runs_of(fixture: Any, thread_id: str) -> list[Any]:
    from lonora_db.schema import RunRow
    from sqlalchemy import select

    async with fixture.runtime.db.sessions() as session:
        return list(await session.scalars(select(RunRow).where(RunRow.thread_id == thread_id)))


async def settle(fixture: Any, credentials: Credentials) -> int:
    from lonora_voice.voice_notes import transcribe_pending

    return await transcribe_pending(
        fixture.runtime.db,
        cast(Any, credentials),
        fixture.owner,
        fixture.settings.artifact_root,
        FakeSpeech,
    )


@pytest.mark.asyncio
async def test_a_voice_note_is_transcribed_before_the_agent_answers():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    FakeSpeech.calls, FakeSpeech.failing_models = [], {"gpt-4o-mini-transcribe"}
    try:
        agent = await fixture.agent("Listener")
        thread = await fixture.conversation(agent)
        artifact_id = await upload(fixture, thread["id"])
        nonce = "voice-" + uuid4().hex
        response = await send_voice(fixture, thread["id"], artifact_id, nonce)
        assert response.status_code == 202, response.text
        sent = response.json()
        message = sent["message"]
        assert message["content"] == "" and sent["run_ids"] == []
        assert message["rich_content"]["parts"] == [
            {
                "type": "voice",
                "artifact_id": artifact_id,
                "duration": 4.2,
                "peaks": PEAKS,
                "transcript_status": "pending",
            }
        ]
        # The Agent is not asked to answer an empty message.
        assert await runs_of(fixture, thread["id"]) == []
        assert len(await events_of(fixture, "message.created", thread["id"])) == 1
        # The same client nonce is the same message.
        again = (await send_voice(fixture, thread["id"], artifact_id, nonce)).json()
        assert again["deduplicated"] and again["message"]["id"] == message["id"]
        inbox = cast(list[dict[str, Any]], await fixture.request("GET", "/threads/inbox"))
        entry = next(item for item in inbox if item["thread_id"] == thread["id"])
        assert entry["last_message"]["kind"] == "voice"

        # The owner's chosen reply language is the transcription hint (none: detected).
        from lonora_db.schema import OwnerProfileRow
        from sqlalchemy import select

        async with fixture.runtime.db.sessions() as session, session.begin():
            profile = await session.scalar(
                select(OwnerProfileRow).where(OwnerProfileRow.owner_id == fixture.owner)
            )
            if profile is None:
                profile = OwnerProfileRow(owner_id=fixture.owner)
                session.add(profile)
            profile.reply_language = "en"
        assert await settle(fixture, Credentials()) >= 1
        # The configured fallback, the owner's language and the recorder's container.
        assert [call["model"] for call in FakeSpeech.calls][:2] == [
            "gpt-4o-mini-transcribe",
            "whisper-1",
        ]
        assert FakeSpeech.calls[1]["language"] == "en"
        assert FakeSpeech.calls[1]["media_type"] == "audio/webm"
        assert FakeSpeech.calls[1]["audio"] == b"OggS-fixture-audio"
        updated = await events_of(fixture, "message.updated", thread["id"])
        assert len(updated) == 1
        assert updated[0].payload["content"] == FakeSpeech.transcript
        assert updated[0].payload["rich_content"]["parts"][0]["transcript_status"] == "done"
        runs = await runs_of(fixture, thread["id"])
        assert len(runs) == 1 and runs[0].input_seq == message["seq"]
        queued = await events_of(fixture, "run.queued", thread["id"])
        assert queued[0].cursor > updated[0].cursor
        # Settled once; a retried send now reports the admitted Run.
        await settle(fixture, Credentials())
        assert len(await events_of(fixture, "message.updated", thread["id"])) == 1
        again = (await send_voice(fixture, thread["id"], artifact_id, nonce)).json()
        assert again["run_ids"] == [runs[0].id]
        history = cast(
            list[dict[str, Any]], await fixture.request("GET", f"/threads/{thread['id']}/messages")
        )
        assert history[-1]["content"] == FakeSpeech.transcript
        from lonora_agent.context.history import history_context

        async with fixture.runtime.db.sessions() as session:
            context = await history_context(session, thread["id"], message["seq"])
        assert context[-1].content == FakeSpeech.transcript
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_failed_transcript_admits_the_run_with_the_server_note():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    FakeSpeech.calls, FakeSpeech.failing_models = [], set()
    try:
        agent = await fixture.agent("Deaf")
        thread = await fixture.conversation(agent)
        artifact_id = await upload(fixture, thread["id"], "audio/ogg")
        response = await send_voice(fixture, thread["id"], artifact_id, "voice-" + uuid4().hex)
        message = response.json()["message"]
        # No OpenAI credentials: no provider call, the note fails.
        assert await settle(fixture, Credentials(configured=False)) >= 1
        assert FakeSpeech.calls == []
        updated = await events_of(fixture, "message.updated", thread["id"])
        assert updated[0].payload["content"] == ""
        assert updated[0].payload["rich_content"]["parts"][0]["transcript_status"] == "failed"
        runs = await runs_of(fixture, thread["id"])
        assert len(runs) == 1
        from lonora_agent.context.history import history_context

        async with fixture.runtime.db.sessions() as session:
            context = await history_context(session, thread["id"], message["seq"])
        assert context[-1].content == VOICE_NOTE_FAILED_TEXT
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_voice_note_needs_the_owners_audio_uploaded_to_this_thread():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Strict")
        thread = await fixture.conversation(agent)
        other = await fixture.conversation(await fixture.agent("Other"))
        elsewhere = await upload(fixture, other["id"])
        response = await send_voice(fixture, thread["id"], elsewhere, "v-" + uuid4().hex)
        assert response.status_code == 422 and response.json()["code"] == "voice_artifact_invalid"
        pdf = await upload(fixture, thread["id"], "application/pdf")
        response = await send_voice(fixture, thread["id"], pdf, "v-" + uuid4().hex)
        assert response.status_code == 422 and response.json()["code"] == "voice_artifact_invalid"
        response = await send_voice(fixture, thread["id"], new_id(), "v-" + uuid4().hex)
        assert response.status_code == 404
        for media_type in ["audio/mp4", "audio/mpeg", "audio/wav"]:
            artifact_id = await upload(fixture, thread["id"], media_type)
            response = await send_voice(fixture, thread["id"], artifact_id, "v-" + uuid4().hex)
            assert response.status_code == 202, media_type
        # Leave no pending note behind for the other cases.
        assert await settle(fixture, Credentials(configured=False)) >= 3
    finally:
        await fixture.close()


async def call_messages(fixture: Any, thread_id: str) -> list[Any]:
    from lonora_db.schema import MessageRow
    from sqlalchemy import select

    async with fixture.runtime.db.sessions() as session:
        return list(
            await session.scalars(
                select(MessageRow).where(
                    MessageRow.thread_id == thread_id, MessageRow.role == "system"
                )
            )
        )


@pytest.mark.asyncio
async def test_an_ended_call_is_logged_once_and_starts_no_run():
    database()
    from check_streaming import Fixture
    from lonora_db.schema import VoiceSessionRow

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Caller")
        thread = await fixture.conversation(agent)
        never, connected = new_id(), new_id()
        async with fixture.runtime.db.sessions() as session, session.begin():
            for identifier, state in [
                (never, {}),
                (connected, {"connected_at": time.time() - 65}),
            ]:
                session.add(
                    VoiceSessionRow(
                        id=identifier,
                        owner_id=fixture.owner,
                        agent_id=agent["id"],
                        thread_id=thread["id"],
                        payload={"mode": "gpt_live", "status": "connected", "model": "m"},
                        state=state,
                        version=1,
                    )
                )
        # A call that never connected leaves no bubble.
        await fixture.request("DELETE", f"/voice/sessions/{never}")
        assert await call_messages(fixture, thread["id"]) == []
        for _ in range(2):
            await fixture.request("DELETE", f"/voice/sessions/{connected}")
        logged = await call_messages(fixture, thread["id"])
        assert len(logged) == 1
        assert logged[0].content == "مكالمة صوتية" and logged[0].agent_id == agent["id"]
        part = logged[0].rich_content["parts"][0]
        assert part["type"] == "call" and part["direction"] == "outgoing"
        assert part["missed"] is False and 64 <= part["duration_seconds"] <= 70
        created = await events_of(fixture, "message.created", thread["id"])
        assert [event.payload["id"] for event in created] == [logged[0].id]
        assert await runs_of(fixture, thread["id"]) == []
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_an_answered_agent_call_is_logged_incoming_once():
    """An agent's call the owner accepted is the agent's call (the agent's side) by an
    explicit link from the answering session; a call the owner places right after an
    accepted, unanswered request is still outgoing (no guessing by time)."""
    database()
    from check_streaming import Fixture
    from lonora_contracts.voice import VoiceSessionCreate
    from lonora_core.user_error import LonoraError
    from lonora_db.schema import VoiceSessionRow
    from lonora_voice.incoming import MODE
    from lonora_voice.sessions import answer_incoming

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Caller back")
        thread = await fixture.conversation(agent)
        request, answered, placed = new_id(), new_id(), new_id()
        async with fixture.runtime.db.sessions() as session, session.begin():
            session.add(
                VoiceSessionRow(
                    id=request,
                    owner_id=fixture.owner,
                    agent_id=agent["id"],
                    thread_id=thread["id"],
                    payload={"mode": MODE, "status": "accepted", "device_id": new_id()},
                    state={},
                    version=1,
                )
            )
        # The owner places a call while the accepted request waits: outgoing.
        async with fixture.runtime.db.sessions() as session, session.begin():
            session.add(
                VoiceSessionRow(
                    id=placed,
                    owner_id=fixture.owner,
                    agent_id=agent["id"],
                    thread_id=thread["id"],
                    payload={"mode": "gpt_live", "status": "connected", "model": "m"},
                    state={"connected_at": time.time() - 20},
                    version=1,
                )
            )
        await fixture.request("DELETE", f"/voice/sessions/{placed}")
        # The answering session links the request explicitly, once.
        body = VoiceSessionCreate(
            agent_id=agent["id"],
            thread_id=thread["id"],
            sdp="v=0",
            client_nonce="answer",
            incoming_call_id=request,
        )
        async with fixture.runtime.db.sessions() as session, session.begin():
            await answer_incoming(session, fixture.owner, body, answered)
            session.add(
                VoiceSessionRow(
                    id=answered,
                    owner_id=fixture.owner,
                    agent_id=agent["id"],
                    thread_id=thread["id"],
                    payload={
                        "mode": "gpt_live",
                        "status": "connected",
                        "model": "m",
                        "incoming_call_id": request,
                    },
                    state={"connected_at": time.time() - 30},
                    version=1,
                )
            )
        async with fixture.runtime.db.sessions() as session, session.begin():
            row = await session.get(VoiceSessionRow, request)
            assert row is not None and row.payload["answered_session_id"] == answered
            # A second session cannot answer the same call.
            with pytest.raises(LonoraError) as twice:
                await answer_incoming(session, fixture.owner, body, new_id())
            assert twice.value.code == "incoming_call_already_answered"
        # Ending runs twice per call; the bubble is written once.
        for _ in range(2):
            await fixture.request("DELETE", f"/voice/sessions/{answered}")
        logged = await call_messages(fixture, thread["id"])
        directions = [message.rich_content["parts"][0]["direction"] for message in logged]
        assert directions == ["outgoing", "incoming"]
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_a_declined_or_missed_incoming_call_is_logged_once():
    database()
    from check_streaming import Fixture
    from lonora_contracts.incoming_calls import IncomingCallPolicy
    from lonora_db.schema import DeviceCredentialRow, VoiceSessionRow
    from lonora_voice.incoming import MODE, incoming_tick, set_preferences

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Ringer")
        thread = await fixture.conversation(agent)
        device = new_id()
        declined, expired = new_id(), new_id()
        async with fixture.runtime.db.sessions() as session, session.begin():
            session.add(
                DeviceCredentialRow(
                    id=device,
                    owner_id=fixture.owner,
                    name="Test device",
                    credential_id="fixture-credential-" + device,
                    public_key="fixture-not-authentication",
                    sign_count=0,
                    revoked=False,
                )
            )
            await set_preferences(
                session, fixture.owner, IncomingCallPolicy(enabled=True, device_id=device)
            )
            for identifier, expires in [
                (declined, utcnow() + timedelta(seconds=60)),
                (expired, utcnow() - timedelta(seconds=1)),
            ]:
                session.add(
                    VoiceSessionRow(
                        id=identifier,
                        owner_id=fixture.owner,
                        agent_id=agent["id"],
                        thread_id=thread["id"],
                        payload={
                            "mode": MODE,
                            "status": "ringing",
                            "attention_id": new_id(),
                            "reason": "Urgent verified account safety change",
                            "device_id": device,
                            "expires_at": expires.isoformat(),
                        },
                        state={"delivery": "provider_unconfigured"},
                        version=1,
                    )
                )
        for _ in range(2):
            result = await fixture.request(
                "POST",
                f"/voice/incoming/{declined}/respond",
                {"action": "reject", "device_id": device},
            )
            assert result["status"] == "rejected"
        await incoming_tick(fixture.runtime.db, fixture.owner)
        await incoming_tick(fixture.runtime.db, fixture.owner)
        logged = await call_messages(fixture, thread["id"])
        assert len(logged) == 2
        for message in logged:
            assert message.content == "مكالمة صوتية فائتة"
            assert message.rich_content["parts"] == [
                {"type": "call", "direction": "incoming", "duration_seconds": 0, "missed": True}
            ]
        assert await runs_of(fixture, thread["id"]) == []
    finally:
        await fixture.close()
