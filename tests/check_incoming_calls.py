"""Disposable PostgreSQL replay, restart, ownership and delivery failure checks."""

import asyncio
from datetime import timedelta
from typing import Any

from check_streaming import Fixture
from lonora_contracts.domain import new_id, utcnow
from lonora_contracts.incoming_calls import IncomingCallPolicy
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import AttentionRow, DeviceCredentialRow, EventRow, VoiceSessionRow
from lonora_db.transactions import SettingsRepository
from lonora_voice.incoming import (
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

    async def send(self, **values: Any) -> None:
        key = str(values["idempotency_key"])
        if key not in self.requests:
            self.effects += 1
            self.requests.add(key)
        if self.fail_after_delivery:
            self.fail_after_delivery = False
            raise TimeoutError("scripted ambiguous delivery")


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
                assert row and row.state["delivery"] == "retry_pending"
                row.state = {**row.state, "retry_at": (utcnow() - timedelta(seconds=1)).isoformat()}
            await asyncio.gather(
                incoming_tick(restarted, f.owner, provider),
                incoming_tick(f.runtime.db, f.owner, provider),
            )
            assert provider.effects == 1
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
        finally:
            await restarted.close()
        print(
            "incoming calls: PostgreSQL concurrent replay/restart/dedup/ownership/TTL/consent passed"
        )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
