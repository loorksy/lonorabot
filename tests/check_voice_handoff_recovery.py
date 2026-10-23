"""Live contract fixtures with actual PostgreSQL replay, revision and restart checks.

No microphone or paid provider requests, simulated broker mutations or live orders.
"""

import asyncio
import time
from copy import deepcopy
from uuid import uuid4

from check_streaming import Fixture
from lonora_core.user_error import LonoraError
from lonora_db.client import Database
from lonora_db.schema import MessageRow, RunRow, SteeringRow, TradeApprovalRow, VoiceSessionRow
from lonora_db.trade_approvals import decide
from lonora_providers.credentials import ProviderCredentials
from lonora_voice.realtime import RealtimeVoiceSession
from sqlalchemy import select


async def main() -> None:
    fixture = await Fixture().open()
    recovered_db = None
    checks = 0
    try:
        agent = await fixture.agent("Voice handoff recovery")
        thread = await fixture.conversation(agent)
        db = fixture.runtime.db
        identity = str(uuid4())
        gateway = "handoff-gateway"
        credentials = ProviderCredentials(db, fixture.runtime.services(fixture.owner).secrets)
        async with db.sessions() as session, session.begin():
            session.add(
                VoiceSessionRow(
                    id=identity,
                    owner_id=fixture.owner,
                    agent_id=agent["id"],
                    thread_id=thread["id"],
                    payload={
                        "mode": "gpt_live",
                        "status": "connected",
                        "remote_id": "explicit-fixture",
                    },
                    state={
                        "gateway": gateway,
                        "input": [],
                        "output": [],
                        "input_offset": -1,
                        "last_activity": time.time(),
                    },
                )
            )
        voice = RealtimeVoiceSession(db, credentials, identity, gateway)

        async def speech(event_id: str, start: float, end: float, delta: str) -> None:
            await voice.update(
                {
                    "type": "session.input_transcript.delta",
                    "event_id": event_id,
                    "start_ms": start,
                    "end_ms": end,
                    "delta": delta,
                }
            )

        async def delegation(event_id: str, offset: float) -> None:
            await voice.update(
                {
                    "type": "session.delegation.created",
                    "event_id": "source-" + event_id,
                    "offset_ms": offset,
                    "delegation": {"id": event_id, "target": "client"},
                }
            )

        async def settled() -> None:
            async with voice.db.sessions() as session, session.begin():
                row = await session.get(VoiceSessionRow, identity, with_for_update=True)
                assert row is not None
                state = deepcopy(row.state)
                state["input_changed_at"] = time.time() - 2
                for task in state["delegations"].values():
                    task["received_at"] = time.time() - 2
                    task["stable_since"] = time.time() - 2
                row.state = state
            await voice.delegate()

        # Tail-before-head, offset after speech (silence), then replayed events.
        await speech("tail", 400, 900, "gold.")
        await delegation("first", 1500)
        await voice.delegate()
        async with db.sessions() as session:
            assert not list(
                await session.scalars(select(RunRow).where(RunRow.thread_id == thread["id"]))
            )
        await speech("head", 0, 400, "Analyze ")
        await settled()
        await speech("head", 0, 400, "Analyze ")
        await delegation("first", 1500)
        await voice.delegate()
        async with db.sessions() as session:
            messages = list(
                await session.scalars(
                    select(MessageRow)
                    .where(MessageRow.thread_id == thread["id"])
                    .order_by(MessageRow.seq)
                )
            )
            runs = list(
                await session.scalars(select(RunRow).where(RunRow.thread_id == thread["id"]))
            )
            assert [item.content for item in messages] == ["Analyze gold."] and len(runs) == 1
            run_id = runs[0].id
            assert runs[0].model_metadata["voice_handoff"]["finalized"] is False
            assert runs[0].model_metadata["voice_handoff"]["source_event_ids"] == ["head", "tail"]
        checks += 1

        # A fresh engine/runtime object recovers only persisted receipts; concurrent replay
        # across both old/new observers cannot admit a duplicate user message or Run.
        recovered_db = Database.connect(fixture.settings.database_url)
        voice = RealtimeVoiceSession(recovered_db, credentials, identity, gateway)
        await asyncio.gather(voice.delegate(), voice.delegate())
        await delegation("a-lexically-earlier-replay", 1500)
        await speech("new-delivery-id-for-head", 0, 400, "Analyze ")
        await voice.delegate()
        async with db.sessions() as session:
            assert (
                len(
                    list(
                        await session.scalars(
                            select(MessageRow).where(MessageRow.thread_id == thread["id"])
                        )
                    )
                )
                == 1
            )
            assert (
                len(
                    list(
                        await session.scalars(
                            select(RunRow).where(RunRow.thread_id == thread["id"])
                        )
                    )
                )
                == 1
            )
        checks += 1

        # New speech stays in the actual active task, with stale prior spoken results fenced.
        async with db.sessions() as session, session.begin():
            run = await session.get(RunRow, run_id, with_for_update=True)
            assert run is not None
            run.status = "running"
        await speech("followup", 1600, 2100, "Use the one-minute timeframe.")
        await delegation("followup", 2400)
        await settled()
        async with db.sessions() as session:
            row = await session.get(VoiceSessionRow, identity)
            assert row is not None
            assert row.state["delegations"]["first"]["status"] == "superseded"
            assert row.state["delegations"]["followup"]["run_ids"] == [run_id]
            assert (
                len(
                    list(
                        await session.scalars(
                            select(SteeringRow).where(SteeringRow.run_id == run_id)
                        )
                    )
                )
                == 1
            )
        checks += 1

        # A late new source fragment is an explicit revision, never a blind replay.
        approval_id = str(uuid4())
        async with db.sessions() as session, session.begin():
            session.add(
                TradeApprovalRow(
                    id=approval_id,
                    owner_id=fixture.owner,
                    agent_id=agent["id"],
                    thread_id=thread["id"],
                    run_id=run_id,
                    call_id="superseded-voice-intent",
                    requests=[],
                    results=[],
                    status="pending",
                )
            )
        await speech("late-tail", 2100, 2200, " Compare it with hourly data.")
        await settled()
        async with db.sessions() as session:
            row = await session.get(VoiceSessionRow, identity)
            assert row is not None
            assert row.state["delegations"]["followup"]["revision"] == 2
            assert row.state["delegations"]["followup"]["run_ids"] == [run_id]
            messages = list(
                await session.scalars(
                    select(MessageRow)
                    .where(MessageRow.thread_id == thread["id"])
                    .order_by(MessageRow.seq)
                )
            )
            assert len(messages) == 3 and messages[-1].content.endswith(
                "Compare it with hourly data."
            )
            approval = await session.get(TradeApprovalRow, approval_id)
            assert approval and approval.status == "cancelled"
        async with db.sessions() as session, session.begin():
            try:
                await decide(session, fixture.owner, approval_id, "approve")
            except LonoraError as error:
                assert error.code == "trade_approval_already_decided"
            else:
                raise AssertionError("Late source correction left stale approval actionable")
        checks += 1

        # Contradicting a source event cannot silently revise a financial observation.
        await speech("late-tail", 2100, 2200, " Open a trade.")
        await delegation("conflict", 3000)
        await settled()
        async with db.sessions() as session:
            row = await session.get(VoiceSessionRow, identity)
            assert row is not None
            assert (
                row.state["delegations"]["conflict"]["handoff_error"] == "transcript_event_conflict"
            )
            assert (
                len(
                    list(
                        await session.scalars(
                            select(MessageRow).where(MessageRow.thread_id == thread["id"])
                        )
                    )
                )
                == 3
            )
        checks += 1

        # Stale Gateway and call closure cannot submit new work or cancel the existing task.
        async with db.sessions() as session, session.begin():
            row = await session.get(VoiceSessionRow, identity, with_for_update=True)
            assert row is not None
            row.state = {**row.state, "gateway": "replacement"}
        await speech("stale", 3200, 3400, "Unobserved stale event")
        await voice.delegate()
        assert await voice.tick() is False and voice.lost_lease
        async with db.sessions() as session:
            run = await session.get(RunRow, run_id)
            assert run is not None
            assert run.status == "running"
            row = await session.get(VoiceSessionRow, identity)
            assert row is not None
            assert not any(item["event_id"] == "stale" for item in row.state["input"])
        checks += 1
        print(f"Voice handoff recovery: {checks} PostgreSQL acceptance scenarios passed")
    finally:
        if recovered_db:
            await recovered_db.close()
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
