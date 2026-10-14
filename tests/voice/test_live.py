"""GPT-Live contract fixtures with real PostgreSQL admission and agent work."""

import asyncio
import hashlib
import json
import os
import time
from collections.abc import AsyncGenerator
from pathlib import Path
from typing import Any
from uuid import uuid4

import httpx
import pytest
import pytest_asyncio
from lonora_adapters.voice.realtime import OpenAILiveAdapter
from lonora_api.app import create_app
from lonora_api.env import get_settings
from lonora_contracts.voice import VoiceSessionCreate
from lonora_core.user_error import LonoraError
from lonora_db.schema import MessageRow, RunRow, VoiceSessionRow
from lonora_providers.credentials import ProviderCredentials
from lonora_voice.realtime import RealtimeVoiceSession, text_chunks
from lonora_voice.sessions import (
    cancel_voice_initialization,
    create_voice_session,
    end_voice_session,
)
from sqlalchemy import select
from sqlalchemy.engine import make_url


@pytest_asyncio.fixture
async def workspace(monkeypatch: pytest.MonkeyPatch) -> AsyncGenerator[dict[str, Any]]:
    url = make_url(os.environ.get("LONORA_DATABASE_URL", ""))
    if not (
        url.drivername.startswith("postgresql")
        and (url.database or "").endswith(("_ci", "_test", "_verify"))
    ):
        pytest.fail("Voice checks require an explicit disposable PostgreSQL URL.")
    app = create_app(get_settings())
    runtime = app.state.runtime
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="https://lonora.test"
    ) as client:
        credentials = {"email": "ci@example.com", "password": "ci-only-owner-password"}
        if not (await client.get("/api/onboarding")).json()["owner_initialized"]:
            response = await client.post(
                "/api/onboarding",
                json={
                    **credentials,
                    "bootstrap_token": get_settings().bootstrap_token.get_secret_value(),
                },
            )
            assert response.status_code == 201
        login = await client.post("/api/auth/login", json=credentials)
        assert login.status_code == 200
        owner = login.json()["owner"]["id"]
        client.headers["X-CSRF-Token"] = login.json()["csrf"]
        agent = (
            await client.post("/api/agents", json={"name": "Voice fixture " + uuid4().hex[:12]})
        ).json()
        thread = (await client.post(f"/api/agents/{agent['id']}/conversation")).json()
        provider = ProviderCredentials(runtime.db, runtime.services(owner).secrets)

        async def resolve(_self: ProviderCredentials, _provider: str) -> str:
            return "explicit-fixture-key-not-a-real-provider-key"

        monkeypatch.setattr(ProviderCredentials, "resolve", resolve)
        try:
            yield {
                "app": app,
                "runtime": runtime,
                "client": client,
                "owner": owner,
                "agent": agent["id"],
                "thread": thread["id"],
                "credentials": provider,
            }
        finally:
            await client.delete(f"/api/agents/{agent['id']}")
            await runtime.close()


def intent(workspace: dict[str, Any], nonce: str | None = None) -> VoiceSessionCreate:
    return VoiceSessionCreate(
        agent_id=workspace["agent"],
        thread_id=workspace["thread"],
        sdp="v=0\r\nfixture-offer",
        client_nonce=nonce or uuid4().hex,
    )


@pytest.mark.asyncio
async def test_official_http_contract_and_sanitized_errors() -> None:
    calls: list[dict[str, Any]] = []

    async def respond(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "https://api.openai.com/v1/live/sessions"
        assert request.headers["authorization"] == "Bearer fixture"
        calls.append(json.loads(request.content))
        return httpx.Response(
            201, json={"session": {"id": "live_fixture"}, "transport": {"sdp": "v=0-answer"}}
        )

    async with httpx.AsyncClient(transport=httpx.MockTransport(respond)) as client:
        result = await OpenAILiveAdapter("fixture", client).create(
            {"model": "gpt-live-1", "delegation": {"type": "client"}}, "v=0-offer"
        )
    assert result["session"]["id"] == "live_fixture"
    assert calls == [
        {
            "session": {"model": "gpt-live-1", "delegation": {"type": "client"}},
            "transport": {"type": "webrtc", "sdp": "v=0-offer"},
        }
    ]
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(
            lambda _: httpx.Response(403, json={"error": "private details"})
        )
    ) as client:
        with pytest.raises(LonoraError) as failed:
            await OpenAILiveAdapter("fixture", client).create({}, "offer")
    assert failed.value.code == "model_credentials_rejected"


@pytest.mark.asyncio
async def test_concurrent_paid_admission_is_once(
    workspace: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    request = intent(workspace)
    runtime = workspace["runtime"]
    called = 0

    async def negotiate(
        _self: OpenAILiveAdapter, config: dict[str, Any], _sdp: str
    ) -> dict[str, Any]:
        nonlocal called
        called += 1
        assert config["delegation"] == {"type": "client"}
        assert config["store"] is False
        await asyncio.sleep(0.05)
        return {"session": {"id": "live_fixture"}, "transport": {"sdp": "answer"}}

    monkeypatch.setattr(OpenAILiveAdapter, "create", negotiate)
    session_id = hashlib.sha256(
        (workspace["owner"] + ":" + request.client_nonce).encode()
    ).hexdigest()[:36]

    async def observer() -> None:
        for _ in range(100):
            async with runtime.db.sessions() as session, session.begin():
                row = await session.get(VoiceSessionRow, session_id, with_for_update=True)
                if row and row.payload.get("status") == "joining":
                    row.payload = {**row.payload, "status": "connected"}
                    return
            await asyncio.sleep(0.02)
        raise AssertionError("Observer never saw committed admission")

    watch = asyncio.create_task(observer())
    replies = await asyncio.gather(
        *(
            create_voice_session(runtime.db, workspace["credentials"], workspace["owner"], request)
            for _ in range(5)
        )
    )
    await watch
    assert called == 1
    assert all(reply == {"session_id": session_id, "sdp": "answer"} for reply in replies)


@pytest.mark.asyncio
async def test_ambiguous_paid_failure_cannot_be_retried(
    workspace: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    called = 0

    async def ambiguous(
        _self: OpenAILiveAdapter, _config: dict[str, Any], _sdp: str
    ) -> dict[str, Any]:
        nonlocal called
        called += 1
        raise LonoraError("voice_connection_failed", 502)

    monkeypatch.setattr(OpenAILiveAdapter, "create", ambiguous)
    request = intent(workspace)
    for _ in range(2):
        with pytest.raises(LonoraError):
            await create_voice_session(
                workspace["runtime"].db, workspace["credentials"], workspace["owner"], request
            )
    assert called == 1


@pytest.mark.asyncio
async def test_cancel_before_admission_allocates_nothing(
    workspace: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    called = False

    async def unexpected(
        _self: OpenAILiveAdapter, _config: dict[str, Any], _sdp: str
    ) -> dict[str, Any]:
        nonlocal called
        called = True
        raise AssertionError("Cancelled request negotiated paid call")

    monkeypatch.setattr(OpenAILiveAdapter, "create", unexpected)
    request = intent(workspace)
    await cancel_voice_initialization(
        workspace["runtime"].db, workspace["owner"], request.client_nonce
    )
    with pytest.raises(LonoraError) as failed:
        await create_voice_session(
            workspace["runtime"].db, workspace["credentials"], workspace["owner"], request
        )
    assert failed.value.code == "voice_session_closed"
    assert not called


async def resident(workspace: dict[str, Any]) -> RealtimeVoiceSession:
    session_id = str(uuid4())
    async with workspace["runtime"].db.sessions() as session, session.begin():
        session.add(
            VoiceSessionRow(
                id=session_id,
                owner_id=workspace["owner"],
                agent_id=workspace["agent"],
                thread_id=workspace["thread"],
                payload={"mode": "gpt_live", "status": "connected", "remote_id": "fixture"},
                state={
                    "gateway": "voice-fixture",
                    "input": [],
                    "output": [],
                    "input_offset": -1,
                    "last_activity": time.time(),
                },
            )
        )
    return RealtimeVoiceSession(
        workspace["runtime"].db, workspace["credentials"], session_id, "voice-fixture"
    )


@pytest.mark.asyncio
async def test_delegated_transcript_is_durable_once_and_close_keeps_work(
    workspace: dict[str, Any],
) -> None:
    voice = await resident(workspace)
    delta = {
        "type": "session.input_transcript.delta",
        "event_id": "speech-1",
        "start_ms": 0,
        "end_ms": 1200,
        "delta": "Analyze risk without placing an order.",
    }
    await voice.update(delta)
    await voice.update(delta)
    event = {
        "type": "session.delegation.created",
        "offset_ms": 1200,
        "delegation": {"id": "delegation-1", "target": "client"},
    }
    await voice.update(event)
    await voice.update(event)
    await asyncio.gather(voice.delegate(), voice.delegate())
    async with workspace["runtime"].db.sessions() as session:
        messages = list(
            (
                await session.scalars(
                    select(MessageRow).where(
                        MessageRow.thread_id == workspace["thread"], MessageRow.role == "user"
                    )
                )
            ).all()
        )
        runs = list(
            (
                await session.scalars(select(RunRow).where(RunRow.thread_id == workspace["thread"]))
            ).all()
        )
    assert [row.content for row in messages] == [delta["delta"]]
    assert len(runs) == 1 and runs[0].status == "queued"
    await end_voice_session(workspace["runtime"].db, workspace["owner"], voice.session_id)
    await voice.delegate()
    assert not await voice.tick()
    async with workspace["runtime"].db.sessions() as session:
        run = await session.get(RunRow, runs[0].id)
        assert run and run.status == "queued"


@pytest.mark.asyncio
async def test_close_before_delegation_does_not_submit_new_agent_work(
    workspace: dict[str, Any],
) -> None:
    voice = await resident(workspace)
    await voice.update(
        {
            "type": "session.input_transcript.delta",
            "event_id": "speech-before-close",
            "start_ms": 0,
            "end_ms": 1200,
            "delta": "Analyze my portfolio risk.",
        }
    )
    await voice.update(
        {
            "type": "session.delegation.created",
            "offset_ms": 1200,
            "delegation": {"id": "pending-before-close", "target": "client"},
        }
    )
    await end_voice_session(workspace["runtime"].db, workspace["owner"], voice.session_id)
    # A Gateway tick may have admitted another delegate pass just before DELETE
    # committed. A closing call must not turn the buffered speech into new work.
    await asyncio.gather(voice.delegate(), voice.delegate())
    async with workspace["runtime"].db.sessions() as session:
        messages = list(
            (
                await session.scalars(
                    select(MessageRow).where(MessageRow.thread_id == workspace["thread"])
                )
            ).all()
        )
        runs = list(
            (
                await session.scalars(select(RunRow).where(RunRow.thread_id == workspace["thread"]))
            ).all()
        )
    assert messages == []
    assert runs == []


@pytest.mark.asyncio
async def test_incomplete_transcript_fails_closed_and_future_request_can_continue(
    workspace: dict[str, Any],
) -> None:
    voice = await resident(workspace)
    await voice.update(
        {
            "type": "session.input_transcript.delta",
            "event_id": "speech-short",
            "start_ms": 0,
            "end_ms": 300,
            "delta": "Buy ",
        }
    )
    await voice.update(
        {
            "type": "session.delegation.created",
            "offset_ms": 1000,
            "delegation": {"id": "incomplete", "target": "client"},
        }
    )
    async with workspace["runtime"].db.sessions() as session, session.begin():
        row = await session.get(VoiceSessionRow, voice.session_id, with_for_update=True)
        assert row
        state = dict(row.state)
        state["delegations"]["incomplete"]["received_at"] = time.time() - 10
        row.state = {**state, "fixture_revision": 1}
    await voice.delegate()
    async with workspace["runtime"].db.sessions() as session:
        assert not (
            await session.scalars(select(RunRow).where(RunRow.thread_id == workspace["thread"]))
        ).all()
        row = await session.get(VoiceSessionRow, voice.session_id)
        assert row and row.state["delegations"]["incomplete"]["status"] == "result"
    await voice.update(
        {
            "type": "session.input_transcript.delta",
            "event_id": "speech-complete",
            "start_ms": 1100,
            "end_ms": 2000,
            "delta": "Only analyze my portfolio risk.",
        }
    )
    await voice.update(
        {
            "type": "session.delegation.created",
            "offset_ms": 2000,
            "delegation": {"id": "complete", "target": "client"},
        }
    )
    await voice.delegate()
    async with workspace["runtime"].db.sessions() as session:
        messages = (
            await session.scalars(
                select(MessageRow).where(
                    MessageRow.thread_id == workspace["thread"], MessageRow.role == "user"
                )
            )
        ).all()
        assert [row.content for row in messages] == ["Only analyze my portfolio risk."]


@pytest.mark.asyncio
async def test_gateway_lease_fences_transcript_and_results(workspace: dict[str, Any]) -> None:
    voice = await resident(workspace)
    async with workspace["runtime"].db.sessions() as session, session.begin():
        row = await session.get(VoiceSessionRow, voice.session_id, with_for_update=True)
        assert row
        row.state = {**row.state, "gateway": "replacement-gateway"}
    await voice.update(
        {
            "type": "session.input_transcript.delta",
            "event_id": "stale",
            "delta": "stale order",
            "end_ms": 100,
        }
    )
    await voice.delegate()
    assert not await voice.tick() and voice.lost_lease
    async with workspace["runtime"].db.sessions() as session:
        row = await session.get(VoiceSessionRow, voice.session_id)
        assert row and row.state["input"] == []


@pytest.mark.asyncio
async def test_final_usage_and_ack_are_durable_idempotently(workspace: dict[str, Any]) -> None:
    voice = await resident(workspace)
    async with workspace["runtime"].db.sessions() as session, session.begin():
        row = await session.get(VoiceSessionRow, voice.session_id, with_for_update=True)
        assert row
        row.state = {
            **row.state,
            "delegations": {
                "task": {
                    "status": "result",
                    "event_id": "result-1",
                    "next_chunk": 0,
                    "chunks": ["done"],
                }
            },
        }
    acknowledgement = {"type": "session.commentary.appended", "client_event_id": "result-1"}
    await voice.update(acknowledgement)
    await voice.update(acknowledgement)
    await voice.update({"type": "session.closed", "usage": {"seconds": 13}})
    async with workspace["runtime"].db.sessions() as session:
        row = await session.get(VoiceSessionRow, voice.session_id)
        assert row
        assert row.state["delegations"]["task"]["next_chunk"] == 1
        assert row.state["usage"] == {"seconds": 13} and row.state["finalized"] is True
        assert row.payload["status"] == "closed"


def test_commentary_byte_limits_and_long_result_disclosure() -> None:
    chunks = text_chunks("تحليل الأسواق " * 800)
    assert all(len(chunk.encode()) <= 480 for chunk in chunks)
    assert "full backend result" in chunks[-1]


@pytest.mark.asyncio
async def test_apk_route_cannot_fall_through_to_spa(tmp_path: Path) -> None:
    settings = get_settings().model_copy(
        update={"android_apk_path": tmp_path / "lonora.apk", "web_root": tmp_path}
    )
    (tmp_path / "index.html").write_text("SPA login")
    app = create_app(settings)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app), base_url="http://fixture"
        ) as client:
            response = await client.get("/download/lonora.apk")
            assert response.status_code == 404 and "SPA login" not in response.text
            settings.android_apk_path.write_bytes(b"PK\x03\x04fixture-test-only")
            response = await client.get("/download/lonora.apk")
            assert response.status_code == 200 and response.content.startswith(b"PK\x03\x04")
            assert response.headers["content-type"] == "application/vnd.android.package-archive"
            assert response.headers["x-content-type-options"] == "nosniff"
            assert (await client.head("/download/lonora.apk")).content == b""
            settings.android_apk_path.write_text("SPA login")
            assert (await client.get("/download/lonora.apk")).status_code == 503
    finally:
        await app.state.runtime.close()
