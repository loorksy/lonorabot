"""Per-agent delivery rules (owner decision Q47): in-app alerts, calls and a daily limit.

The rules only narrow how an agent's own alerts reach the owner: a critical or
action_required item always shows (Q4), and nothing here grants any authority.
"""

import os
from typing import Any
from uuid import uuid4

import pytest
from lonora_contracts.agent_delivery import AgentDeliveryRules
from pydantic import ValidationError


def test_rules_default_to_the_owner_wide_policy():
    rules = AgentDeliveryRules()
    assert rules.in_app and rules.calls and rules.daily_limit is None
    with pytest.raises(ValidationError):
        AgentDeliveryRules(daily_limit=0)
    with pytest.raises(ValidationError):
        AgentDeliveryRules(daily_limit=101)
    assert "trading" not in AgentDeliveryRules.model_fields


def database() -> None:
    if not os.environ.get("LONORA_DATABASE_URL"):
        pytest.skip("The delivery rules use the real migrated PostgreSQL schema.")


async def _notify(fixture: Any, agent: dict[str, Any], thread: dict[str, Any], importance: str):
    from lonora_contracts.attention import OwnerNotifyRequest
    from lonora_db.attention import notify_owner

    async with fixture.runtime.db.sessions() as session, session.begin():
        return await notify_owner(
            session,
            fixture.owner,
            agent["id"],
            thread["id"],
            OwnerNotifyRequest(
                importance=importance,
                summary="Gold moved past the level " + uuid4().hex[:6],
                dedupe_key="rules-" + uuid4().hex,
            ),
        )


@pytest.mark.asyncio
async def test_route_reads_and_saves_rules_and_refuses_another_owners_agent():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Rules " + uuid4().hex[:6])
        read = await fixture.client.get(f"/api/agents/{agent['id']}/notifications")
        assert read.status_code == 200, read.text
        assert read.json() == {"in_app": True, "calls": True, "daily_limit": None}
        saved = await fixture.client.put(
            f"/api/agents/{agent['id']}/notifications",
            json={"in_app": True, "calls": False, "daily_limit": 5},
        )
        assert saved.status_code == 200, saved.text
        again = await fixture.client.get(f"/api/agents/{agent['id']}/notifications")
        assert again.json() == {"in_app": True, "calls": False, "daily_limit": 5}
        listed = await fixture.client.get("/api/agents/notifications")
        assert listed.status_code == 200
        assert listed.json()[agent["id"]] == {"in_app": True, "calls": False, "daily_limit": 5}
        missing = await fixture.client.put(
            f"/api/agents/{uuid4()}/notifications", json={"in_app": False}
        )
        assert missing.status_code == 404
        invalid = await fixture.client.put(
            f"/api/agents/{agent['id']}/notifications", json={"daily_limit": 0}
        )
        assert invalid.status_code == 422
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_daily_limit_and_in_app_off_keep_alerts_in_activity_but_urgent_ones_show():
    database()
    from check_streaming import Fixture

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Limited " + uuid4().hex[:6])
        thread = await fixture.conversation(agent)
        await fixture.client.put(
            f"/api/agents/{agent['id']}/notifications", json={"daily_limit": 1}
        )
        first = await _notify(fixture, agent, thread, "important_change")
        assert first["status"] in {"pending", "ready"}, first
        second = await _notify(fixture, agent, thread, "important_change")
        assert second["status"] == "agent_daily_limit" and second["attention_id"] is None, second
        urgent = await _notify(fixture, agent, thread, "action_required")
        assert urgent["status"] == "ready", urgent
        quiet = await fixture.agent("Quiet " + uuid4().hex[:6])
        quiet_thread = await fixture.conversation(quiet)
        await fixture.client.put(f"/api/agents/{quiet['id']}/notifications", json={"in_app": False})
        held = await _notify(fixture, quiet, quiet_thread, "important_change")
        assert held["status"] == "agent_in_app_off" and held["attention_id"] is None, held
        critical = await _notify(fixture, quiet, quiet_thread, "critical")
        assert critical["attention_id"], critical
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_calls_off_means_the_agent_never_rings():
    database()
    from check_streaming import Fixture
    from lonora_contracts.domain import new_id, utcnow
    from lonora_contracts.incoming_calls import IncomingCallPolicy
    from lonora_core.user_error import LonoraError
    from lonora_db.schema import AttentionRow, DeviceCredentialRow, VoiceSessionRow
    from lonora_voice.incoming import (
        preferences,
        request_call,
        require_current_consent,
        set_preferences,
    )

    fixture = await Fixture().open()
    device = new_id()
    async with fixture.runtime.db.sessions() as session:
        before = await preferences(session, fixture.owner)
    try:
        agent = await fixture.agent("No calls " + uuid4().hex[:6])
        thread = await fixture.conversation(agent)
        attention = new_id()
        async with fixture.runtime.db.sessions() as session, session.begin():
            session.add(
                DeviceCredentialRow(
                    id=device,
                    owner_id=fixture.owner,
                    name="Test device",
                    credential_id="fixture-" + device,
                    public_key="fixture-not-authentication",
                    sign_count=0,
                    revoked=False,
                )
            )
            await session.flush()
            await set_preferences(
                session, fixture.owner, IncomingCallPolicy(enabled=True, device_id=device)
            )
            session.add(
                AttentionRow(
                    id=attention,
                    owner_id=fixture.owner,
                    agent_id=agent["id"],
                    thread_id=thread["id"],
                    importance="critical",
                    code="agent_notification",
                    status="ready",
                    logical_key=attention,
                    coalesce_key=attention,
                    parameters={},
                    source_events=[],
                    source_count=1,
                    version=1,
                    due_at=utcnow(),
                )
            )
        # With calls on, the invitation rings.
        async with fixture.runtime.db.sessions() as session, session.begin():
            ringing = await request_call(
                session,
                fixture.owner,
                attention,
                "Urgent verified account safety change",
                agent_id=agent["id"],
                thread_id=thread["id"],
            )
            ringing_id = ringing.id
        await fixture.client.put(f"/api/agents/{agent['id']}/notifications", json={"calls": False})
        # The call already ringing loses its consent the moment calls are turned off.
        with pytest.raises(LonoraError) as stale:
            async with fixture.runtime.db.sessions() as session:
                row = await session.get(VoiceSessionRow, ringing_id)
                assert row is not None
                await require_current_consent(session, row)
        assert stale.value.code == "incoming_call_agent_disabled"
        # And a new one never rings.
        second = new_id()
        async with fixture.runtime.db.sessions() as session, session.begin():
            source = await session.get(AttentionRow, attention)
            assert source is not None
            session.add(
                AttentionRow(
                    id=second,
                    owner_id=fixture.owner,
                    agent_id=agent["id"],
                    thread_id=thread["id"],
                    importance="critical",
                    code="agent_notification",
                    status="ready",
                    logical_key=second,
                    coalesce_key=second,
                    parameters={},
                    source_events=[],
                    source_count=1,
                    version=1,
                    due_at=utcnow(),
                )
            )
        with pytest.raises(LonoraError) as refused:
            async with fixture.runtime.db.sessions() as session, session.begin():
                await request_call(
                    session,
                    fixture.owner,
                    second,
                    "Urgent verified account safety change",
                    agent_id=agent["id"],
                    thread_id=thread["id"],
                )
        assert refused.value.code == "incoming_call_agent_disabled"
    finally:
        async with fixture.runtime.db.sessions() as session, session.begin():
            await set_preferences(session, fixture.owner, before)
        await fixture.close()


@pytest.mark.asyncio
async def test_owner_notify_tells_the_agent_when_its_rules_kept_the_alert_in_activity():
    database()
    from check_streaming import Fixture
    from lonora_adapter_kit.types import ToolCall
    from lonora_tools.loader import load_tools

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Rule notes " + uuid4().hex[:6])
        await fixture.client.put(f"/api/agents/{agent['id']}/notifications", json={"in_app": False})
        thread = await fixture.conversation(agent)
        run = await fixture.run(agent, thread)
        context = await fixture.lease(run)
        result = await load_tools().execute(
            ToolCall(
                id="notify-" + uuid4().hex,
                name="owner_notify",
                arguments={
                    "importance": "important_change",
                    "summary": "Gold moved past the level " + uuid4().hex[:6],
                    "dedupe_key": "rules-" + uuid4().hex,
                },
            ),
            context,
        )
        assert result["status"] == "agent_in_app_off", result
        assert "no notification was shown" in result["note"], result
    finally:
        await fixture.close()


@pytest.mark.asyncio
async def test_owner_notify_tells_the_agent_when_its_daily_limit_kept_the_alert_in_activity():
    database()
    from check_streaming import Fixture
    from lonora_adapter_kit.types import ToolCall
    from lonora_tools.loader import load_tools

    fixture = await Fixture().open()
    try:
        agent = await fixture.agent("Rule limit " + uuid4().hex[:6])
        await fixture.client.put(
            f"/api/agents/{agent['id']}/notifications", json={"daily_limit": 1}
        )
        thread = await fixture.conversation(agent)
        results = []
        for _ in range(2):
            run = await fixture.run(agent, thread)
            context = await fixture.lease(run)
            results.append(
                await load_tools().execute(
                    ToolCall(
                        id="notify-" + uuid4().hex,
                        name="owner_notify",
                        arguments={
                            "importance": "important_change",
                            "summary": "Gold moved past the level " + uuid4().hex[:6],
                            "dedupe_key": "limit-" + uuid4().hex,
                        },
                    ),
                    context,
                )
            )
        first, second = results
        assert first["status"] in {"pending", "ready"} and first["attention_id"], first
        assert second["status"] == "agent_daily_limit", second
        assert second["attention_id"] is None, second
        assert "daily alert limit" in second["note"], second
    finally:
        await fixture.close()
