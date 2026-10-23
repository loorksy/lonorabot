"""Disposable PostgreSQL replay, restart, ownership and delivery failure checks."""

import asyncio
from datetime import timedelta
from typing import Any

from check_streaming import Fixture
from lonora_contracts.domain import new_id, utcnow
from lonora_contracts.incoming_calls import IncomingCallPolicy
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import AgentRow, AttentionRow, DeviceCredentialRow, EventRow, VoiceSessionRow
from lonora_db.transactions import SettingsRepository
from lonora_voice.incoming import (
    ProviderAccepted,
    call_data,
    incoming_tick,
    request_call,
    set_preferences,
    transition,
)
from sqlalchemy import func, select


class FakeDelivery:
    def __init__(self):
        self.requests: set[str] = set()
        self.effects = 0
        self.fail_after_delivery = False
        self.calls = 0
        self.cancel_after_delivery = False
        self.before_send: Any = None

    async def send(self, **values: Any) -> ProviderAccepted:
        self.calls += 1
        if self.before_send is not None:
            await self.before_send(values)
        key = str(values["idempotency_key"])
        if key not in self.requests:
            self.effects += 1
            self.requests.add(key)
        if self.fail_after_delivery:
            self.fail_after_delivery = False
            raise TimeoutError("scripted ambiguous delivery")
        if self.cancel_after_delivery:
            raise asyncio.CancelledError("scripted worker loss after delivery")
        return ProviderAccepted()


async def main():
    f = await Fixture().open()
    try:
        agent = await f.agent("Incoming attention fixture")
        thread = await f.conversation(agent)
        device = new_id()
        async with f.runtime.db.sessions() as session, session.begin():
            session.add(
                DeviceCredentialRow(
                    id=device,
                    owner_id=f.owner,
                    name="Test device",
                    credential_id="fixture-credential",
                    public_key="fixture-not-authentication",
                    sign_count=0,
                    revoked=False,
                )
            )
            await set_preferences(
                session,
                f.owner,
                IncomingCallPolicy(enabled=True, device_id=device, minimum_interval_seconds=60),
            )
            await SettingsRepository().put(session, "trading_control", {"emergency_stop": True})

        async def attention():
            identifier = new_id()
            async with f.runtime.db.sessions() as session, session.begin():
                session.add(
                    AttentionRow(
                        id=identifier,
                        owner_id=f.owner,
                        agent_id=agent["id"],
                        thread_id=thread["id"],
                        importance="critical",
                        code="emergency_stop",
                        status="ready",
                        logical_key=identifier,
                        coalesce_key=identifier,
                        parameters={},
                        source_events=[],
                        source_count=1,
                        version=1,
                        due_at=utcnow(),
                    )
                )
            return identifier

        source = await attention()

        async def request():
            async with f.runtime.db.sessions() as session, session.begin():
                return call_data(
                    await request_call(
                        session,
                        f.owner,
                        source,
                        "Urgent verified account safety change",
                        agent_id=agent["id"],
                        thread_id=thread["id"],
                    )
                )

        first, duplicate = await asyncio.gather(request(), request())
        assert first["id"] == duplicate["id"] and not first["execution_authorized"]
        call_id = first["id"]
        async with f.runtime.db.sessions() as session:
            assert (
                await session.scalar(
                    select(func.count())
                    .select_from(VoiceSessionRow)
                    .where(VoiceSessionRow.payload["mode"].as_string() == "incoming_request")
                )
                == 1
            )
        assert await incoming_tick(f.runtime.db, f.owner) == 0
        async with f.runtime.db.sessions() as session:
            row = await session.get(VoiceSessionRow, call_id)
            assert row and row.state["delivery"] == "provider_unconfigured"
        # A fresh Database instance is the restarted process; PostgreSQL is authoritative.
        restarted = Database.connect(f.settings.database_url)
        provider = FakeDelivery()
        provider.fail_after_delivery = True
        try:
            assert await incoming_tick(restarted, f.owner, provider) == 0
            async with restarted.sessions() as session, session.begin():
                row = await session.get(VoiceSessionRow, call_id)
                assert row and row.state["delivery"] == "uncertain"
                assert row.state["delivery_error_type"] == "TimeoutError"
            await asyncio.gather(
                incoming_tick(restarted, f.owner, provider),
                incoming_tick(f.runtime.db, f.owner, provider),
            )
            assert provider.effects == 1 and provider.calls == 1
            assert await incoming_tick(restarted, f.owner, provider) == 0
            async with restarted.sessions() as session, session.begin():
                try:
                    await transition(session, "another-owner", call_id, "accept", device)
                except LonoraError as error:
                    assert error.code == "incoming_call_not_found"
                else:
                    raise AssertionError("cross-owner acceptance")
            response = await f.request(
                "POST",
                f"/voice/incoming/{call_id}/respond",
                {"action": "accept", "device_id": device},
            )
            assert response["status"] == "accepted" and not response["execution_authorized"]
            assert (await request())["status"] == "accepted"
            assert await incoming_tick(restarted, f.owner, provider) == 0
            async with restarted.sessions() as session:
                events = await session.scalar(
                    select(func.count())
                    .select_from(EventRow)
                    .where(EventRow.kind == "voice.incoming.updated")
                )
                assert events == 2
            # New transitions are anti-spam bounded even after restart.
            new_source = await attention()
            async with restarted.sessions() as session, session.begin():
                try:
                    await request_call(session, f.owner, new_source, "Another urgent safety change")
                except LonoraError as error:
                    assert error.code == "incoming_call_rate_limited"
                else:
                    raise AssertionError("rate limit lost after restart")
            # TTL expiry and rejected/cancelled transitions survive process recreation.
            async with restarted.sessions() as session, session.begin():
                row = await session.get(VoiceSessionRow, call_id)
                assert row
                row.payload = {
                    **row.payload,
                    "status": "ringing",
                    "expires_at": (utcnow() - timedelta(seconds=1)).isoformat(),
                }
            await incoming_tick(restarted, f.owner, provider)
            async with restarted.sessions() as session, session.begin():
                row = await transition(session, f.owner, call_id, "accept", device)
                assert row.payload["status"] == "missed"
                row.payload = {
                    **row.payload,
                    "status": "ringing",
                    "expires_at": (utcnow() + timedelta(seconds=45)).isoformat(),
                }
                await transition(session, f.owner, call_id, "reject", device)
            async with restarted.sessions() as session, session.begin():
                row = await transition(session, f.owner, call_id, "accept", device)
                assert row.payload["status"] == "rejected"
                row.payload = {**row.payload, "status": "ringing"}
                await set_preferences(session, f.owner, IncomingCallPolicy())
            await incoming_tick(restarted, f.owner, provider)
            async with restarted.sessions() as session:
                row = await session.get(VoiceSessionRow, call_id)
                assert row and row.payload["status"] == "cancelled"
                assert (await SettingsRepository().get(session, "trading_control"))[
                    "emergency_stop"
                ]

            async def fresh_call():
                # Independent invitations without wall-clock sleeps or rate bypasses in code.
                async with restarted.sessions() as session, session.begin():
                    rows = await session.scalars(
                        select(VoiceSessionRow).where(VoiceSessionRow.owner_id == f.owner)
                    )
                    for old in rows:
                        old.payload = {**old.payload, "status": "cancelled"}
                        old.created_at = utcnow() - timedelta(seconds=61)
                    await set_preferences(
                        session,
                        f.owner,
                        IncomingCallPolicy(
                            enabled=True, device_id=device, minimum_interval_seconds=60
                        ),
                    )
                current_source = await attention()
                async with restarted.sessions() as session, session.begin():
                    return (
                        await request_call(
                            session,
                            f.owner,
                            current_source,
                            "Verified safety change requiring help",
                        )
                    ).id

            acknowledged_id = await fresh_call()
            acknowledged = FakeDelivery()

            async def require_committed_fence(values: dict[str, Any]):
                # A separate connection sees the fence before any external effect.
                async with f.runtime.db.sessions() as session:
                    row = await session.get(VoiceSessionRow, values["call_id"])
                    assert row and row.state["delivery"] == "uncertain"
                    assert row.state["attempt"] == 1
                await asyncio.sleep(0)

            acknowledged.before_send = require_committed_fence
            counts = await asyncio.gather(
                incoming_tick(restarted, f.owner, acknowledged),
                incoming_tick(f.runtime.db, f.owner, acknowledged),
            )
            assert sum(counts) == 1 and acknowledged.calls == 1
            assert await incoming_tick(restarted, f.owner, acknowledged) == 0
            assert await incoming_tick(restarted, f.owner) == 0
            async with restarted.sessions() as session:
                row = await session.get(VoiceSessionRow, acknowledged_id)
                assert row and row.state["delivery"] == "provider_accepted"
                assert "presented_at" not in row.state and "rang_at" not in row.state
                assert row.payload["status"] == "ringing"  # Invitation state, not an OS receipt.
                assert not call_data(row)["execution_authorized"]
                assert (
                    await session.scalar(
                        select(func.count())
                        .select_from(VoiceSessionRow)
                        .where(VoiceSessionRow.payload["mode"].as_string() == "gpt_live")
                    )
                    == 0
                )

            crashed_id = await fresh_call()
            crashed = FakeDelivery()
            crashed.cancel_after_delivery = True
            crashed.before_send = require_committed_fence
            try:
                await incoming_tick(restarted, f.owner, crashed)
            except asyncio.CancelledError:
                pass
            else:
                raise AssertionError("worker cancellation swallowed")
            assert await incoming_tick(f.runtime.db, f.owner, crashed) == 0
            assert await incoming_tick(restarted, f.owner) == 0
            assert crashed.calls == 1 and crashed.effects == 1
            async with restarted.sessions() as session, session.begin():
                row = await session.get(VoiceSessionRow, crashed_id)
                assert row and row.state["delivery"] == "uncertain"
                row.payload = {
                    **row.payload,
                    "expires_at": (utcnow() - timedelta(seconds=1)).isoformat(),
                }
            assert await incoming_tick(restarted, f.owner, crashed) == 0
            async with restarted.sessions() as session:
                row = await session.get(VoiceSessionRow, crashed_id)
                assert row and row.payload["status"] == "missed"

            for legacy_state, expected in [
                ("retry_pending", "uncertain"),
                ("delivered", "provider_accepted"),
            ]:
                legacy_id = await fresh_call()
                async with restarted.sessions() as session, session.begin():
                    row = await session.get(VoiceSessionRow, legacy_id)
                    assert row
                    row.state = {"delivery": legacy_state}
                provider = FakeDelivery()
                assert await incoming_tick(restarted, f.owner, provider) == 0
                assert provider.calls == 0
                async with restarted.sessions() as session:
                    row = await session.get(VoiceSessionRow, legacy_id)
                    assert row and row.state["delivery"] == expected

            # Recheck current consent before a provider ever sees the request.
            await fresh_call()
            async with restarted.sessions() as session, session.begin():
                await set_preferences(session, f.owner, IncomingCallPolicy())
            provider = FakeDelivery()
            assert await incoming_tick(restarted, f.owner, provider) == 0
            assert provider.calls == 0

            expired_id = await fresh_call()
            async with restarted.sessions() as session, session.begin():
                row = await session.get(VoiceSessionRow, expired_id)
                assert row
                row.payload = {
                    **row.payload,
                    "expires_at": (utcnow() - timedelta(seconds=1)).isoformat(),
                }
            assert await incoming_tick(restarted, f.owner, provider) == 0
            assert provider.calls == 0
            async with restarted.sessions() as session:
                row = await session.get(VoiceSessionRow, expired_id)
                assert row and row.payload["status"] == "missed"

            quiet_id = await fresh_call()
            async with restarted.sessions() as session, session.begin():
                await set_preferences(
                    session,
                    f.owner,
                    IncomingCallPolicy(
                        enabled=True,
                        device_id=device,
                        quiet_start_hour=0,
                        quiet_end_hour=0,
                    ),
                )
            assert await incoming_tick(restarted, f.owner, provider) == 0
            assert provider.calls == 0
            async with restarted.sessions() as session:
                row = await session.get(VoiceSessionRow, quiet_id)
                assert row and row.payload["status"] == "cancelled"

            # A queued invitation does not retain authority after the owner's
            # credential, category consent or Agent state changes.
            for revoked_boundary in ("credential", "category", "agent"):
                withdrawn_id = await fresh_call()
                async with restarted.sessions() as session, session.begin():
                    if revoked_boundary == "credential":
                        credential = await session.get(DeviceCredentialRow, device)
                        assert credential
                        credential.revoked = True
                    elif revoked_boundary == "category":
                        await set_preferences(
                            session,
                            f.owner,
                            IncomingCallPolicy(enabled=True, device_id=device, critical=False),
                        )
                    else:
                        current_agent = await session.get(AgentRow, agent["id"])
                        assert current_agent
                        current_agent.paused = True
                withdrawn_provider = FakeDelivery()
                assert await incoming_tick(restarted, f.owner, withdrawn_provider) == 0
                assert withdrawn_provider.calls == 0
                async with restarted.sessions() as session, session.begin():
                    row = await session.get(VoiceSessionRow, withdrawn_id)
                    assert row and row.payload["status"] == "cancelled"
                    credential = await session.get(DeviceCredentialRow, device)
                    current_agent = await session.get(AgentRow, agent["id"])
                    assert credential and current_agent
                    credential.revoked = False
                    current_agent.paused = False
        finally:
            await restarted.close()
        print(
            "incoming calls: PostgreSQL concurrency/restart/uncertainty/provider-ack/ownership/TTL/consent passed"
        )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
