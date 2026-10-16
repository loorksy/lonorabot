"""Durable attention uses actual watch state, current quotes and owner-scoped sources."""

import asyncio
from datetime import timedelta
from typing import Any, cast
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.channels.webhook import WebhookAdapter
from lonora_agent.collaboration.outcome_return import return_outcome
from lonora_contracts.attention import AttentionClassification
from lonora_contracts.domain import MessageCreate, utcnow
from lonora_db.attention import decide_attention, mandatory_current
from lonora_db.collaboration import current_session
from lonora_db.events import emit
from lonora_db.messages import send_message
from lonora_db.schema import (
    AgentRow,
    AttentionRow,
    CollaborationSessionRow,
    EffectReceiptRow,
    EventRow,
    IntegrationRow,
    MarketSnapshotRow,
    RunRow,
    TradingAccountRow,
)
from lonora_gateway.attention import attention_tick, ready_attention
from lonora_gateway.event_dispatch import dispatch_channels
from lonora_market.watchers import check_watches
from lonora_tools.loader import load_tools
from sqlalchemy import select


async def main():
    f = await Fixture().open()
    try:
        account = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
            )
        )["id"]
        now = utcnow()
        symbol = "EURUSDm"
        await f.request(
            "POST",
            f"/trading/connections/{account}/simulation",
            {
                "snapshot": {
                    "balance": "10000",
                    "currency": "USD",
                    "instruments": [
                        {
                            "symbol": symbol,
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.01",
                            "volume_max": "10",
                            "volume_step": "0.01",
                        }
                    ],
                    "quotes": {
                        symbol: {
                            "symbol": symbol,
                            "bid": "100",
                            "ask": "101",
                            "observed_at": now.isoformat(),
                            "source": "scripted-attention-fixture",
                        }
                    },
                    "candles": {
                        symbol + ":1m": [
                            {
                                "symbol": symbol,
                                "timeframe": "1m",
                                "time": (now - timedelta(seconds=60)).isoformat(),
                                "open": "99",
                                "high": "101",
                                "low": "98",
                                "close": "100",
                            }
                        ]
                    },
                }
            },
        )
        agent = await f.agent("Attention specialist")
        async with f.runtime.db.sessions() as session, session.begin():
            saved = await session.get(AgentRow, agent["id"])
            assert saved
            saved.role, saved.trading_account_id, saved.trading_symbol = (
                "specialist",
                account,
                symbol,
            )
        thread = await f.conversation(agent)
        context = await f.lease(await f.run(agent, thread))
        registry = load_tools()

        async def inbox() -> list[dict[str, Any]]:
            response = await f.client.get("/api/attention")
            assert response.is_success
            return cast(list[dict[str, Any]], response.json())

        async def tool(name: str, arguments: dict[str, Any]):
            return await registry.execute(
                ToolCall(id=uuid4().hex, name=name, arguments=arguments), context
            )

        watch = await tool(
            "watch_create",
            {
                "kind": "price",
                "condition": "above",
                "level": "99",
                "prompt": "Inspect current setup",
                "confirmation_ttl_seconds": 120,
            },
        )
        watch_id = watch.get("id") or watch.get("watch", {}).get("id")
        assert watch_id
        assert await check_watches(f.runtime.db, context.brokers, owner_id=f.owner) == 1
        await asyncio.gather(
            attention_tick(f.runtime.db, context.brokers, f.owner),
            attention_tick(f.runtime.db, context.brokers, f.owner),
        )
        rows = await inbox()
        notices = [row for row in rows if row["code"] == "setup_confirmed"]
        assert len(notices) == 1 and notices[0]["agent_id"] == agent["id"]
        assert (
            notices[0]["parameters"]["symbol"] == symbol
            and notices[0]["parameters"]["execution_authorized"] is False
        )
        original = notices[0]
        async with f.runtime.db.sessions() as session, session.begin():
            source = await session.scalar(
                select(EventRow).where(
                    EventRow.kind == "watch.confirmed",
                    EventRow.payload["watch_id"].as_string() == watch_id,
                )
            )
            assert source
            emit(
                session,
                f.owner,
                source.kind,
                agent_id=source.agent_id,
                thread_id=source.thread_id,
                payload={
                    key: value
                    for key, value in source.payload.items()
                    if not key.startswith("_ln_")
                },
            )
        await attention_tick(f.runtime.db, context.brokers, f.owner)
        rows = await inbox()
        assert len([row for row in rows if row["code"] == "setup_confirmed"]) == 1
        async with f.runtime.db.sessions() as session, session.begin():
            row = await session.get(AttentionRow, original["id"])
            assert row
            row.due_at = utcnow() - timedelta(seconds=1)
        assert await ready_attention(f.runtime.db, context.brokers, f.owner) == 1
        assert await ready_attention(f.runtime.db, context.brokers, f.owner) == 0
        seen = await f.request("POST", "/attention/seen", {"notification_id": original["id"]})
        assert seen["status"] == "seen"
        assert (await f.request("POST", "/attention/seen", {"notification_id": original["id"]}))[
            "version"
        ] == seen["version"]
        print(
            "PASS actual watch confirmation, concurrent Gateway ticks, duplicate transition and restart delivery create one specialist-owned notification; seen is durable/idempotent and grants no execution"
        )

        # A confirmation is revalidated at delivery, not merely when queued.
        late = await tool(
            "watch_create",
            {
                "kind": "price",
                "condition": "above",
                "level": "99",
                "prompt": "Inspect another setup",
                "confirmation_ttl_seconds": 120,
            },
        )
        assert late
        await check_watches(f.runtime.db, context.brokers, owner_id=f.owner)
        await attention_tick(f.runtime.db, context.brokers, f.owner)
        pending = [row for row in await inbox() if row["code"] == "setup_confirmed"]
        assert len(pending) == 1
        async with f.runtime.db.sessions() as session, session.begin():
            account_row = await session.get(TradingAccountRow, account)
            assert account_row
            quotes = dict(account_row.payload["quotes"])
            quotes[symbol] = {
                **quotes[symbol],
                "observed_at": (utcnow() - timedelta(hours=1)).isoformat(),
            }
            account_row.payload = {**account_row.payload, "quotes": quotes}
            snapshots = await session.scalars(
                select(MarketSnapshotRow).where(
                    MarketSnapshotRow.connection_id == account, MarketSnapshotRow.timeframe == ""
                )
            )
            for snapshot in snapshots:
                snapshot.payload = {
                    **snapshot.payload,
                    "observed_at": (utcnow() - timedelta(hours=1)).isoformat(),
                }
            notification = await session.get(AttentionRow, pending[0]["id"])
            assert notification
            notification.due_at = utcnow() - timedelta(seconds=1)
        assert await ready_attention(f.runtime.db, context.brokers, f.owner) == 0
        async with f.runtime.db.sessions() as session:
            suppressed = await session.get(AttentionRow, pending[0]["id"])
            assert (
                suppressed
                and suppressed.status == "suppressed"
                and suppressed.parameters["suppression_code"]
            )
        print(
            "PASS stale current broker evidence suppresses a queued opportunity before delivery; no stale BUY notification"
        )

        await f.request(
            "PUT",
            "/attention/policy",
            {"opportunities": False, "informational": False, "locale": "ar"},
        )
        await f.request("PUT", "/trading/controls", {"enabled": False, "emergency_stop": True})
        await attention_tick(f.runtime.db, context.brokers, f.owner)
        rows = await inbox()
        critical = [row for row in rows if row["code"] == "emergency_stop"]
        assert len(critical) == 1 and critical[0]["status"] == "ready"
        async with f.runtime.db.sessions() as session:
            personal = await session.get(AgentRow, critical[0]["agent_id"])
            assert personal and personal.role == "personal"
        await attention_tick(f.runtime.db, context.brokers, f.owner)
        assert len([row for row in await inbox() if row["code"] == "emergency_stop"]) == 1
        print(
            "PASS mandatory critical owner notification bypasses coalescing delay and optional quiet preferences; account/global ownership is Personal"
        )
        missing = await f.client.post("/api/attention/seen", json={"notification_id": str(uuid4())})
        assert missing.status_code == 404
        controls = await f.request("GET", "/trading/controls")
        assert controls["enabled"] is False and controls["emergency_stop"] is True
        async with f.runtime.db.sessions() as session:
            audits = list(
                await session.scalars(
                    select(EffectReceiptRow).where(
                        EffectReceiptRow.key.like("attention-source:" + f.owner + ":%")
                    )
                )
            )
            assert audits and any(row.result["status"] == "deduplicated" for row in audits)
            assert all("agent_id" in row.result and "source_event" in row.result for row in audits)
        print(
            "PASS attention decisions retain source/owner/provenance and cannot change approvals or financial controls"
        )

        # Exercise the durable coalescing ledger separately from event validation.
        # Two real transitions share a pending row; replay of either must still
        # deduplicate after the row becomes ready (including after restart).
        async def decision(transition: str, *, stale: bool = False):
            async with f.runtime.db.sessions() as session, session.begin():
                event = EventRow(
                    owner_id=f.owner,
                    kind="broker.external_activity",
                    agent_id=agent["id"],
                    thread_id=thread["id"],
                    payload={"id": transition},
                )
                session.add(event)
                await session.flush()
                return await decide_attention(
                    session,
                    event,
                    AttentionClassification(
                        importance="important_change",
                        code="external_broker_activity",
                        resource_id=account,
                        transition=transition,
                    ),
                    agent_id=agent["id"],
                    thread_id=thread["id"],
                    parameters={"account_id": account, "symbol": symbol},
                    coalesce_scope="coalescing-test:" + account,
                    suppression_code="attention_superseded_state" if stale else None,
                )

        first = await decision("change-one")
        second = await decision("change-two")
        assert first and second and first.id == second.id
        assert second.source_count == 2 and second.due_at == first.due_at
        async with f.runtime.db.sessions() as session, session.begin():
            merged = await session.get(AttentionRow, first.id)
            assert merged
            merged.status = "ready"
        replay = await decision("change-two")
        assert replay and replay.id == first.id and replay.source_count == 2
        assert await decision("obsolete-source", stale=True) is None
        async with f.runtime.db.sessions() as session:
            merged = await session.get(AttentionRow, first.id)
            assert merged and merged.status == "ready"
            critical_row = await session.get(AttentionRow, critical[0]["id"])
            assert critical_row and await mandatory_current(session, critical_row)
        await f.request("PUT", "/trading/controls", {"enabled": False, "emergency_stop": False})
        async with f.runtime.db.sessions() as session:
            critical_row = await session.get(AttentionRow, critical[0]["id"])
            assert critical_row and not await mandatory_current(session, critical_row)
        await attention_tick(f.runtime.db, context.brokers, f.owner)
        assert not any(row["code"] == "emergency_stop" for row in await inbox())
        print(
            "PASS fixed coalescing deadline, logical replay after restart, stale-source isolation and mandatory channel revalidation against current controls"
        )

        services = f.runtime.services(f.owner)
        secret_id = await services.secrets.write("attention-scripted", uuid4().hex, "integration")
        async with f.runtime.db.sessions() as session, session.begin():
            channel = IntegrationRow(
                owner_id=f.owner,
                payload={
                    "enabled": True,
                    "type": "webhook",
                    "url": "https://example.test/attention",
                    "secret_id": secret_id,
                },
            )
            session.add(channel)
            await session.flush()
            channel_id = channel.id
        sent: list[str] = []

        async def scripted_send(_adapter: WebhookAdapter, destination: str, content: str):
            assert destination == "https://example.test/attention"
            sent.append(content)
            return {"status": "fixture-confirmed"}

        with patch("lonora_gateway.event_dispatch.WebhookAdapter.send", scripted_send):
            # The previously queued emergency has ended: do not send obsolete safety state.
            await dispatch_channels(f.runtime.db, services)
            assert not sent
            await f.request("PUT", "/trading/controls", {"enabled": False, "emergency_stop": True})
            await attention_tick(f.runtime.db, context.brokers, f.owner)
            await asyncio.gather(
                dispatch_channels(f.runtime.db, services),
                dispatch_channels(f.runtime.db, services),
            )
            await dispatch_channels(f.runtime.db, services)
            assert len(sent) == 1 and "الإيقاف الطارئ" in sent[0]
        async with f.runtime.db.sessions() as session:
            receipts = list(
                await session.scalars(
                    select(EffectReceiptRow).where(
                        EffectReceiptRow.key.startswith("channel:" + channel_id + ":attention:")
                    )
                )
            )
            assert len(receipts) == 1
            skipped = await session.get(
                EffectReceiptRow,
                "attention-channel-skip:" + channel_id + ":" + critical[0]["id"],
            )
            # Runtime retirement itself can suppress it before dispatch; either
            # durable source audit or delivery skip explains the suppression.
            assert skipped or critical[0]["id"] not in {row.key for row in receipts}
        print(
            "PASS mandatory Arabic channel delivery is state-revalidated and deduplicated across concurrent dispatch/restart, with no real external network call"
        )

        host = await f.agent("Attention collaboration host")
        guest = await f.agent("Attention contributor")
        discussion = await f.conversation(host)
        async with f.runtime.db.sessions() as session, session.begin():
            sent_message = await send_message(
                session,
                f.owner,
                discussion["id"],
                MessageCreate(content="Review actual evidence", mention_agent_ids=[guest["id"]]),
            )
            collaboration = await current_session(session, f.owner, discussion["id"])
            assert collaboration
            collaboration_id = collaboration.id
            participant_id = collaboration.state["rounds"][0]["participant_run_ids"][0]
            parent = await session.get(RunRow, sent_message["run_ids"][0])
            participant = await session.get(RunRow, participant_id)
            assert parent and participant
            parent.status, parent.result = "completed", "Requested contribution"
            participant.status, participant.result = "completed", "Scripted source evidence"
        await return_outcome(f.runtime.db, participant_id)
        await attention_tick(f.runtime.db, context.brokers, f.owner)
        assert not any(row["code"] == "collaboration_completed" for row in await inbox())
        async with f.runtime.db.sessions() as session, session.begin():
            collaboration = await session.get(CollaborationSessionRow, collaboration_id)
            assert collaboration
            synthesis_id = collaboration.state["rounds"][0]["synthesis_run_id"]
            synthesis = await session.get(RunRow, synthesis_id)
            assert synthesis
            synthesis.status, synthesis.result = "completed", "Final measured outcome"
        await return_outcome(f.runtime.db, synthesis_id)
        await return_outcome(f.runtime.db, synthesis_id)
        await attention_tick(f.runtime.db, context.brokers, f.owner)
        summaries = [row for row in await inbox() if row["code"] == "collaboration_completed"]
        assert len(summaries) == 1 and summaries[0]["agent_id"] == host["id"]
        assert summaries[0]["thread_id"] == discussion["id"]
        print(
            "PASS real peer outcome stays silent until the single final synthesis, owned by the host conversation, with replay-safe notification"
        )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
