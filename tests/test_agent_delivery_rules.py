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
