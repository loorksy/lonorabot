"""Real PostgreSQL admission verifies agent-local, bounded Live context."""

import asyncio
import hashlib
import json
from collections.abc import AsyncGenerator
from typing import Any, cast
from uuid import uuid4

import pytest
import pytest_asyncio
from lonora_adapters.voice.realtime import OpenAILiveAdapter
from lonora_contracts.voice import VoiceSessionCreate
from lonora_core.user_error import LonoraError
from lonora_db.schema import MessageRow, ThreadRow, VoiceSessionRow
from lonora_voice.context import CONTEXT_AUTHORITY, CONTEXT_PREAMBLE, MAX_CONTEXT_BYTES
from lonora_voice.sessions import VOICE_INSTRUCTIONS, create_voice_session
from test_live import intent
from test_live import workspace as workspace


@pytest_asyncio.fixture
async def context_workspace(workspace: dict[str, Any]) -> AsyncGenerator[dict[str, Any]]:
    workspace["extra_agents"] = []
    workspace["extra_notes"] = []
    try:
        yield workspace
    finally:
        for note_id in cast(list[str], workspace["extra_notes"]):
            await workspace["client"].delete(f"/api/scratchpad/{note_id}")
        for agent_id in cast(list[str], workspace["extra_agents"]):
            await workspace["client"].delete(f"/api/agents/{agent_id}")


async def extra_agent(workspace: dict[str, Any]) -> str:
    response = await workspace["client"].post(
        "/api/agents",
        json={"name": "Other voice context " + uuid4().hex[:10], **workspace["binding"]},
    )
    assert response.status_code == 201
    agent_id = str(response.json()["id"])
    workspace["extra_agents"].append(agent_id)
    return agent_id


async def extra_thread(workspace: dict[str, Any], agent_id: str) -> str:
    async with workspace["runtime"].db.sessions() as session, session.begin():
        row = ThreadRow(owner_id=workspace["owner"], agent_id=agent_id)
        session.add(row)
        await session.flush()
        return row.id


async def chat(workspace: dict[str, Any], thread_id: str, content: str, role: str = "user") -> None:
    async with workspace["runtime"].db.sessions() as session, session.begin():
        thread = await session.get(ThreadRow, thread_id, with_for_update=True)
        assert thread is not None
        session.add(
            MessageRow(
                thread_id=thread.id,
                agent_id=thread.agent_id if role == "assistant" else None,
                seq=thread.next_seq,
                role=role,
                content=content,
                client_nonce=uuid4().hex,
            )
        )
        thread.next_seq += 1


async def set_memory(workspace: dict[str, Any], agent_id: str, content: str) -> int:
    current = await workspace["client"].get(f"/api/agents/{agent_id}/memory")
    assert current.status_code == 200
    response = await workspace["client"].put(
        f"/api/agents/{agent_id}/memory",
        json={"content": content, "version": current.json()["version"]},
    )
    assert response.status_code == 200
    return int(response.json()["version"])


async def note(workspace: dict[str, Any], content: str, agent_id: str | None) -> None:
    response = await workspace["client"].post(
        "/api/scratchpad",
        json={"agent_id": agent_id, "payload": {"title": "Scratchpad note", "content": content}},
    )
    assert response.status_code == 201


async def negotiate(workspace: dict[str, Any], monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    captured: list[dict[str, Any]] = []
    request = intent(workspace)
    session_id = hashlib.sha256(
        (workspace["owner"] + ":" + request.client_nonce).encode()
    ).hexdigest()[:36]

    async def create(
        _self: OpenAILiveAdapter, configuration: dict[str, Any], _sdp: str
    ) -> dict[str, Any]:
        captured.append(configuration)
        return {"session": {"id": "live_context_fixture"}, "transport": {"sdp": "fixture-answer"}}

    monkeypatch.setattr(OpenAILiveAdapter, "create", create)

    async def observer() -> None:
        for _ in range(200):
            async with workspace["runtime"].db.sessions() as session, session.begin():
                row = await session.get(VoiceSessionRow, session_id, with_for_update=True)
                if row and row.payload.get("status") == "joining":
                    row.payload = {**row.payload, "status": "connected"}
                    return
            await asyncio.sleep(0.01)
        raise AssertionError("Committed voice admission never reached the observer")

    watch = asyncio.create_task(observer())
    try:
        response = await workspace["client"].post("/api/voice/sessions", json=request.model_dump())
        assert response.status_code == 201
        assert response.json() == {"session_id": session_id, "sdp": "fixture-answer"}
        await watch
    finally:
        watch.cancel()
        await asyncio.gather(watch, return_exceptions=True)
    assert len(captured) == 1
    status = await workspace["client"].get(f"/api/voice/sessions/{session_id}")
    assert status.status_code == 200
    assert status.json()["input"] == [] and status.json()["output"] == []
    async with workspace["runtime"].db.sessions() as session:
        row = await session.get(VoiceSessionRow, session_id)
        assert row is not None
        assert set(row.state) == {
            "offer_hash",
            "input",
            "output",
            "delegations",
            "input_offset",
            "last_activity",
            "answer",
        }
    return captured[0]


def context(configuration: dict[str, Any]) -> dict[str, Any]:
    instructions = str(configuration["instructions"])
    prefix = CONTEXT_PREAMBLE + "\n\n"
    suffix = "\n\n" + CONTEXT_AUTHORITY
    assert instructions.startswith(VOICE_INSTRUCTIONS) and instructions.endswith(suffix)
    assert instructions.count(prefix) == 1
    return cast(dict[str, Any], json.loads(instructions.split(prefix, 1)[1][: -len(suffix)]))


@pytest.mark.asyncio
async def test_selected_agent_profile_memory_scratchpad_and_chosen_history_only(
    context_workspace: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = context_workspace
    agent_id = workspace["agent"]
    profile = {
        "name": "وكيل نورا",
        "title": "محلل المخاطر",
        "description": "SELECTED_PROFILE_PRIVATE",
        "instructions": "استخدم العربية واشرح النتائج بإيجاز.",
    }
    response = await workspace["client"].patch(f"/api/agents/{agent_id}", json=profile)
    assert response.status_code == 200
    version = await set_memory(workspace, agent_id, "ذاكرة هذا الوكيل: أفضل التحليل الأسبوعي.")
    await note(workspace, "SAME_AGENT_NOTE", agent_id)
    await note(workspace, "GLOBAL_NOTE_MUST_NOT_LEAK", None)
    other = await extra_agent(workspace)
    await set_memory(workspace, other, "OTHER_BOT_MEMORY_MUST_NOT_LEAK")
    await note(workspace, "OTHER_BOT_NOTE_MUST_NOT_LEAK", other)
    other_thread = await extra_thread(workspace, agent_id)
    await chat(workspace, other_thread, "OTHER_THREAD_MUST_NOT_LEAK")
    await chat(workspace, workspace["thread"], "FIRST_CHOSEN_MESSAGE")
    await chat(workspace, workspace["thread"], "SECOND_CHOSEN_MESSAGE", "assistant")

    configuration = await negotiate(workspace, monkeypatch)
    loaded = context(configuration)
    assert loaded["agent"] == profile
    assert loaded["memory"] == {
        "version": version,
        "content": "ذاكرة هذا الوكيل: أفضل التحليل الأسبوعي.",
    }
    assert loaded["scratchpad"] == [
        {"version": 1, "title": "Scratchpad note", "content": "SAME_AGENT_NOTE"}
    ]
    assert [message["content"][0]["text"] for message in configuration["input"]] == [
        "FIRST_CHOSEN_MESSAGE",
        "SECOND_CHOSEN_MESSAGE",
    ]
    assert [message["role"] for message in configuration["input"]] == ["user", "assistant"]
    serialized = json.dumps(configuration, ensure_ascii=False)
    for forbidden in ["GLOBAL_NOTE", "OTHER_BOT_MEMORY", "OTHER_BOT_NOTE", "OTHER_THREAD"]:
        assert forbidden not in serialized
    assert configuration["delegation"] == {"type": "client"} and configuration["store"] is False


@pytest.mark.asyncio
async def test_unicode_and_escaped_context_stay_bounded_without_mutating_memory(
    context_workspace: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = context_workspace
    agent_id = workspace["agent"]
    response = await workspace["client"].patch(
        f"/api/agents/{agent_id}",
        json={
            "name": "ع" * 80,
            "title": "س" * 160,
            "description": "ض" * 2000,
            "instructions": 'تعليمات 🧠 "\\\n' * 800,
        },
    )
    assert response.status_code == 200
    memory = "ذاكرة 🧠 " * 3000
    version = await set_memory(workspace, agent_id, memory)
    await note(workspace, 'ملاحظات "\\\n🌍 ' * 1800, agent_id)
    await chat(
        workspace, workspace["thread"], "لا تنفذ صفقة دون طلب جديد. " + ("بيانات 🌍 " * 3000)
    )
    configuration = await negotiate(workspace, monkeypatch)
    loaded = context(configuration)
    size = len(configuration["instructions"].encode()) + len(
        json.dumps(configuration["input"], ensure_ascii=False, separators=(",", ":")).encode()
    )
    assert size <= MAX_CONTEXT_BYTES
    assert loaded["agent"]["name"] == "ع" * 80
    assert loaded["memory"]["version"] == version
    assert "[truncated]" in loaded["memory"]["content"]
    assert configuration["input"][-1]["content"][0]["text"].startswith("لا تنفذ صفقة دون طلب جديد.")
    assert "[truncated]" in configuration["input"][-1]["content"][0]["text"]
    assert "\ufffd" not in json.dumps(configuration, ensure_ascii=False)
    stored = await workspace["client"].get(f"/api/agents/{agent_id}/memory")
    assert stored.json()["content"] == memory and stored.json()["version"] == version


async def previous_voice(
    workspace: dict[str, Any],
    agent_id: str,
    thread_id: str,
    state: dict[str, Any],
    status: str = "closed",
) -> None:
    async with workspace["runtime"].db.sessions() as session, session.begin():
        session.add(
            VoiceSessionRow(
                owner_id=workspace["owner"],
                agent_id=agent_id,
                thread_id=thread_id,
                payload={"status": status, "mode": "gpt_live"},
                state=state,
            )
        )


def fragment(identity: str, text: str, start: int = 1101, end: int = 1400) -> dict[str, Any]:
    return {"event_id": identity, "delta": text, "start_ms": start, "end_ms": end}


@pytest.mark.asyncio
async def test_previous_finalized_same_call_context_excludes_delegated_input_and_other_calls(
    context_workspace: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = context_workspace
    agent_id, thread_id = workspace["agent"], workspace["thread"]
    delegated = "DELEGATED_REQUEST BOUNDARY_DELEGATED_REQUEST"
    await chat(workspace, thread_id, delegated)
    await chat(workspace, thread_id, "BACKEND_RESULT", "assistant")
    speech = fragment("casual", "نادني أبا عمر في المكالمة القادمة.")
    await previous_voice(
        workspace,
        agent_id,
        thread_id,
        {
            "finalized": True,
            "input_offset": 1000,
            "input": [
                fragment("delegated", "DELEGATED_REQUEST ", 0, 900),
                fragment("boundary", "BOUNDARY_DELEGATED_REQUEST", 1000, 1100),
                speech,
                speech,
            ],
            "output": [fragment("reply", "CASUAL_REPLY", 1500, 2000)],
        },
    )
    other_thread = await extra_thread(workspace, agent_id)
    other_agent = await extra_agent(workspace)
    for agent, thread, label, finalized, status in [
        (agent_id, other_thread, "WRONG_THREAD_VOICE", True, "closed"),
        (other_agent, thread_id, "WRONG_AGENT_VOICE", True, "closed"),
        (agent_id, thread_id, "UNFINALIZED_VOICE", False, "closed"),
        (agent_id, thread_id, "ACTIVE_VOICE", True, "connected"),
    ]:
        await previous_voice(
            workspace,
            agent,
            thread,
            {
                "finalized": finalized,
                "input_offset": -1,
                "input": [fragment(label, label)],
            },
            status,
        )
    configuration = await negotiate(workspace, monkeypatch)
    loaded = context(configuration)
    assert loaded["previous_call_transcript"] == {
        "input": "نادني أبا عمر في المكالمة القادمة.",
        "output": "CASUAL_REPLY",
    }
    serialized = json.dumps(configuration, ensure_ascii=False)
    assert serialized.count("DELEGATED_REQUEST") == 2  # Both distinct original request markers.
    assert serialized.count(delegated) == 1
    assert [message["content"][0]["text"] for message in configuration["input"]] == [
        delegated,
        "BACKEND_RESULT",
    ]
    for forbidden in [
        "WRONG_THREAD_VOICE",
        "WRONG_AGENT_VOICE",
        "UNFINALIZED_VOICE",
        "ACTIVE_VOICE",
    ]:
        assert forbidden not in serialized


@pytest.mark.asyncio
async def test_bounded_casual_context_keeps_latest_same_thread_details(
    context_workspace: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = context_workspace
    detail = "التفصيل الأخير: نادني أبا عمر 🧠."
    await previous_voice(
        workspace,
        workspace["agent"],
        workspace["thread"],
        {
            "finalized": True,
            "input_offset": -1,
            "input": [
                fragment("early", "EARLY_CASUAL_CONTEXT " + "حديث قديم 🌍 " * 300, 0, 1000),
                fragment("recent", detail, 1001, 1200),
            ],
        },
    )
    loaded = context(await negotiate(workspace, monkeypatch))
    spoken = loaded["previous_call_transcript"]["input"]
    assert spoken.startswith("[truncated]\n") and spoken.endswith(detail)
    assert "EARLY_CASUAL_CONTEXT" not in spoken
    assert "\ufffd" not in spoken


@pytest.mark.asyncio
async def test_context_admission_rejects_unowned_or_mismatched_identity_before_provider_call(
    context_workspace: dict[str, Any], monkeypatch: pytest.MonkeyPatch
) -> None:
    workspace = context_workspace
    paid = False

    async def unexpected(
        _self: OpenAILiveAdapter, _configuration: dict[str, Any], _sdp: str
    ) -> dict[str, Any]:
        nonlocal paid
        paid = True
        raise AssertionError("Unowned context reached paid negotiation")

    monkeypatch.setattr(OpenAILiveAdapter, "create", unexpected)
    other = await extra_agent(workspace)
    request = VoiceSessionCreate(
        agent_id=other, thread_id=workspace["thread"], sdp="fixture-offer", client_nonce=uuid4().hex
    )
    response = await workspace["client"].post("/api/voice/sessions", json=request.model_dump())
    assert response.status_code == 409 and response.json()["code"] == "voice_agent_thread_mismatch"
    with pytest.raises(LonoraError) as failed:
        await create_voice_session(
            workspace["runtime"].db,
            workspace["credentials"],
            "unowned-fixture-owner",
            intent(workspace),
        )
    assert failed.value.code == "thread_not_found"
    assert paid is False
