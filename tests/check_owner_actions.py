"""Owner action cards on disposable PostgreSQL with the simulation broker.

Exercises W15-2 end to end through the agent tool, the attention projection (runtime
cards, no model involved) and the owner-session decision route: trusting a feed and
resolving an uncertain operation, with re-validation, idempotency, dedupe, the per-agent
cap and expiry. No live broker, MetaApi key or real order is involved.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import httpx
from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_core.user_error import LonoraError
from lonora_db.schema import (
    AttentionRow,
    EventRow,
    MessageRow,
    OwnerActionRow,
    TradingAccountRow,
    TradingJournalRow,
)
from lonora_db.trusted_sources import feed_trusted
from lonora_gateway.attention import attention_tick
from lonora_tools.loader import load_tools
from lonora_trading.operation_events import operation_event
from sqlalchemy import func, select

GOLD = "XAUUSD.r"


class LostAcknowledgement(SimulationBroker):
    """The broker applies the order but its acknowledgement never arrives."""

    async def execute(
        self, request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        await super().execute(request, before_send)
        raise TimeoutError("explicit acknowledgement loss after the simulated effect")


def snapshot() -> dict[str, Any]:
    return {
        "currency": "USD",
        "balance": "10000",
        "instruments": [
            {
                "symbol": GOLD,
                "digits": 2,
                "tick_size": "0.01",
                "volume_min": "0.1",
                "volume_max": "10",
                "volume_step": "0.1",
            }
        ],
        "quotes": {GOLD: quote()},
    }


def quote() -> dict[str, Any]:
    return {
        "symbol": GOLD,
        "bid": "2000.00",
        "ask": "2000.50",
        "observed_at": utcnow().isoformat(),
        "source": "explicit-owner-actions-fixture",
        "loss_tick_value": "1",
        "profit_tick_value": "1",
        "tick_value_basis": "account_currency_per_lot",
    }


async def main() -> None:
    fixture = await Fixture().open()
    db = fixture.runtime.db
    try:
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "cards-" + uuid4().hex, "enabled": True},
        )
        account = cast(str, connection["id"])
        await fixture.request(
            "POST", f"/trading/connections/{account}/simulation", {"snapshot": snapshot()}
        )
        services = fixture.runtime.services(fixture.owner)
        await services.brokers.get(fixture.owner, account)
        registry = load_tools()

        async def refresh() -> None:
            async with db.sessions() as session, session.begin():
                row = await session.get(TradingAccountRow, account, with_for_update=True)
                assert row is not None
                row.payload = {**row.payload, "quotes": {GOLD: quote()}}

        async def raw(
            method: str, path: str, body: dict[str, Any] | None = None
        ) -> tuple[int, dict[str, Any]]:
            response = await fixture.client.request(method, "/api" + path, json=body)
            return response.status_code, response.json()

        async def raw_list(path: str) -> list[dict[str, Any]]:
            response = await fixture.client.get("/api" + path)
            assert response.is_success, response.text
            return cast(list[dict[str, Any]], response.json())

        async def card(identifier: str) -> OwnerActionRow:
            async with db.sessions() as session:
                row = await session.get(OwnerActionRow, identifier)
                assert row is not None
                return row

        async def cards_in(thread_id: str) -> list[dict[str, Any]]:
            response = await fixture.client.get(
                "/api/owner-actions", params={"thread_id": thread_id}
            )
            assert response.is_success, response.text
            return cast(list[dict[str, Any]], response.json())

        async def decide(identifier: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
            return await raw("POST", f"/owner-actions/{identifier}/decision", body)

        async def acknowledgements(thread_id: str) -> list[str]:
            async with db.sessions() as session:
                return list(
                    await session.scalars(
                        select(MessageRow.content)
                        .where(
                            MessageRow.thread_id == thread_id,
                            MessageRow.role == "assistant",
                        )
                        .order_by(MessageRow.seq)
                    )
                )

        async def project() -> None:
            for _ in range(4):
                await attention_tick(db, services.brokers, fixture.owner)

        # The owner's message starts the agent's run; the agent proposes the cards.
        agent = await fixture.agent("Card proposer", supervised=True)
        thread = await fixture.conversation(agent)
        sent = await fixture.request(
            "POST",
            f"/threads/{thread['id']}/messages",
            {"content": "Trust this news site please", "client_nonce": "cards-" + uuid4().hex},
        )
        run = {"id": sent["run_ids"][0], "agent_id": agent["id"], "thread_id": thread["id"]}
        context = await fixture.lease(run)

        async def propose(arguments: dict[str, Any], call_id: str | None = None) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(
                    id=call_id or "card-" + uuid4().hex,
                    name="owner_action_propose",
                    arguments=arguments,
                ),
                context,
            )

        async def propose_error(arguments: dict[str, Any]) -> str:
            try:
                await propose(arguments)
            except LonoraError as error:
                return error.code
            raise AssertionError("Expected a refusal")

        async def trusted(domain: str) -> bool:
            async with db.sessions() as session:
                return await feed_trusted(session, fixture.owner, domain)

        # 1. A trust card: one tap; proposing changes nothing; confirming is idempotent;
        #    the same change once made is refused as not needed.
        feed = "cards-" + uuid4().hex[:8] + ".example.com"
        trust = {"kind": "trust_source", "source_kind": "feed_domain", "identifier": feed}
        proposal = await propose(trust)
        identifier = proposal["owner_action"]["id"]
        assert proposal["owner_must_tap"] is True and proposal["execution_authorized"] is False
        assert (await card(identifier)).status == "pending"
        assert await trusted(feed) is False  # Proposing changes nothing.
        listed = await cards_in(thread["id"])
        assert [row["id"] for row in listed] == [identifier]
        source = {"kind": "feed_domain", "label": feed, "subscribe": False}
        assert listed[0]["facts"]["source"] == source, listed[0]["facts"]
        assert listed[0]["timeline_seq"] is not None and listed[0]["requires_passkey"] is False
        before = len(await acknowledgements(thread["id"]))
        status, first = await decide(identifier, {"decision": "confirm"})
        assert status == 200 and first["status"] == "confirmed", first
        assert first["decided_via"] == "tap"
        assert await trusted(feed) is True
        status, again = await decide(identifier, {"decision": "confirm"})
        assert status == 200 and again["status"] == "confirmed"
        assert again["decided_at"] == first["decided_at"]
        status, conflict = await decide(identifier, {"decision": "cancel"})
        assert status == 409 and conflict["code"] == "owner_action_already_decided"
        posted = await acknowledgements(thread["id"])
        assert len(posted) == before + 1 and "trusted" in posted[-1].lower(), posted
        assert await propose_error(trust) == "owner_action_not_needed_source_already_trusted"
        print("PASS a trust card changes nothing until the tap; confirming is idempotent")

        # 2. No tool path can confirm: the agent's registry only proposes, and the
        #    decision route needs the owner's session.
        names = sorted(name for name in registry.tools if "owner_action" in name)
        assert names == ["owner_action_propose"], names
        other = "cards-" + uuid4().hex[:8] + ".example.com"
        another = {"kind": "trust_source", "source_kind": "feed_domain", "identifier": other}
        pending = (await propose(another))["owner_action"]["id"]
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(fixture.app), base_url="https://streaming.test"
        ) as stranger:
            anonymous = await stranger.post(
                f"/api/owner-actions/{pending}/decision", json={"decision": "confirm"}
            )
        assert anonymous.status_code == 401, anonymous.status_code
        replay = await propose(another)
        assert replay["owner_action"]["id"] == pending and replay["already_shown"] is True
        assert (await card(pending)).status == "pending"
        assert await trusted(other) is False
        status, cancelled = await decide(pending, {"decision": "cancel"})
        assert status == 200 and cancelled["status"] == "cancelled"
        assert await trusted(other) is False
        print("PASS no tool confirms a card; repeated proposals return the card already shown")

        # 6. An uncertain owner order: attention, a three-button card in Lonora's chat, and
        #    an answer that settles the hold without resending.
        lonora = next(row for row in await raw_list("/agents") if row.get("role") == "personal")
        personal = await fixture.request("POST", f"/agents/{lonora['id']}/conversation", {})
        await refresh()
        cached = services.brokers.connections[account]
        services.brokers.connections[account] = (
            cached[0],
            LostAcknowledgement(db, fixture.owner, account),
        )
        operation = "cards-op-" + uuid4().hex
        try:
            result = await services.trading.execute(
                fixture.owner,
                TradeRequest(
                    account_id=account,
                    operation_id=operation,
                    action="buy",
                    symbol=GOLD,
                    volume=Decimal("0.1"),
                    stop_loss=Decimal("1990"),
                ),
            )
            assert result.status == "ambiguous", result
        finally:
            services.brokers.connections[account] = cached
        await project()
        resolve = next(
            row
            for row in await cards_in(personal["id"])
            if row["kind"] == "resolve_operation" and row["status"] == "pending"
        )
        operation_facts = resolve["facts"]["operation"]
        assert operation_facts["symbol"] == GOLD and operation_facts["by_owner"] is True
        async with db.sessions() as session:
            uncertain = list(
                await session.scalars(
                    select(AttentionRow).where(
                        AttentionRow.owner_id == fixture.owner,
                        AttentionRow.code == "operation_uncertain",
                    )
                )
            )
        assert len(uncertain) == 1 and uncertain[0].importance == "action_required"
        assert uncertain[0].status == "ready"
        await refresh()
        try:
            await services.trading.execute(
                fixture.owner,
                TradeRequest(
                    account_id=account,
                    operation_id="cards-held-" + uuid4().hex,
                    action="buy",
                    symbol=GOLD,
                    volume=Decimal("0.1"),
                    stop_loss=Decimal("1990"),
                ),
            )
        except LonoraError as error:
            assert error.code == "broker_reconciliation_required", error.code
        else:
            raise AssertionError("an uncertain operation holds new risk on its market")
        status, missing = await decide(resolve["id"], {"decision": "confirm"})
        assert status == 422 and missing["code"] == "owner_action_outcome_required"
        status, answered = await decide(
            resolve["id"], {"decision": "confirm", "outcome": "executed"}
        )
        assert status == 200 and answered["status"] == "confirmed", answered
        async with db.sessions() as session:
            journal = await session.get(TradingJournalRow, operation)
            assert journal is not None and journal.status == "resolved"
            resolution = journal.result["details"]["resolution"]
            assert resolution["outcome"] == "executed" and resolution["broker_confirmed"] is False
            assert resolution["statement"].startswith("Owner attested via chat card")
            resolved_events = await session.scalar(
                select(func.count())
                .select_from(EventRow)
                .where(
                    EventRow.owner_id == fixture.owner,
                    EventRow.kind == "trading.operation_resolved",
                    EventRow.payload["operation_id"].as_string() == operation,
                )
            )
            assert resolved_events == 1
            sends = await session.get(TradingAccountRow, account)
            assert sends is not None
            assert list(sends.payload.get("operations", {})).count(operation) == 1
        await refresh()
        cleared = await services.trading.execute(
            fixture.owner,
            TradeRequest(
                account_id=account,
                operation_id="cards-after-" + uuid4().hex,
                action="buy",
                symbol=GOLD,
                volume=Decimal("0.1"),
                stop_loss=Decimal("1990"),
            ),
        )
        assert cleared.status == "confirmed", cleared
        posted = await acknowledgements(personal["id"])
        assert any(
            text in posted[-1] for text in ("not broker confirmation", "ليس تأكيدًا من الوسيط")
        ), posted[-1]
        await project()
        async with db.sessions() as session:
            item = await session.get(AttentionRow, uncertain[0].id)
            assert item is not None and item.status == "suppressed"
        print(
            "PASS an uncertain trade raises attention and a resolve card; the answer clears the hold"
        )

        # 7. An agent's uncertain operation lands in that agent's conversation.
        attributed = "cards-agent-op-" + uuid4().hex
        async with db.sessions() as session, session.begin():
            row = TradingJournalRow(
                operation_id=attributed,
                owner_id=fixture.owner,
                account_id=account,
                request_hash="fixture",
                request={"account_id": account, "action": "sell", "symbol": GOLD, "volume": "0.2"},
                status="ambiguous",
                result={
                    "operation_id": attributed,
                    "status": "ambiguous",
                    "code": "broker_result_ambiguous",
                    "details": {
                        "send_state": "sent",
                        "execution": {
                            "agent_id": agent["id"],
                            "run_id": run["id"],
                            "send_authorized": True,
                        },
                    },
                },
                submitted_at=utcnow(),
                updated_at=utcnow(),
            )
            session.add(row)
            await session.flush()
            await operation_event(session, row)
        await project()
        mine = next(
            row
            for row in await cards_in(thread["id"])
            if row["kind"] == "resolve_operation" and row["status"] == "pending"
        )
        assert mine["facts"]["operation"]["by_agent_name"] == agent["name"]
        status, unknown = await decide(mine["id"], {"decision": "confirm", "outcome": "unknown"})
        assert status == 200 and unknown["result"] == {"outcome": "unknown"}
        assert "unknown" in (await acknowledgements(thread["id"]))[-1].lower()
        print("PASS an agent's uncertain operation raises its card in that agent's conversation")

        # A card whose record changed elsewhere is superseded: the owner settles the
        # operation from the journal, so its waiting card no longer asks anything.
        elsewhere = "cards-elsewhere-op-" + uuid4().hex
        async with db.sessions() as session, session.begin():
            row = TradingJournalRow(
                operation_id=elsewhere,
                owner_id=fixture.owner,
                account_id=account,
                request_hash="fixture",
                request={"account_id": account, "action": "buy", "symbol": GOLD, "volume": "0.1"},
                status="ambiguous",
                result={
                    "operation_id": elsewhere,
                    "status": "ambiguous",
                    "code": "broker_result_ambiguous",
                    "details": {
                        "send_state": "sent",
                        "execution": {
                            "agent_id": agent["id"],
                            "run_id": run["id"],
                            "send_authorized": True,
                        },
                    },
                },
                submitted_at=utcnow(),
                updated_at=utcnow(),
            )
            session.add(row)
            await session.flush()
            await operation_event(session, row)
        await project()
        async with db.sessions() as session:
            waiting_card = (
                await session.execute(
                    select(OwnerActionRow).where(
                        OwnerActionRow.subject == "operation:" + elsewhere,
                        OwnerActionRow.status == "pending",
                    )
                )
            ).scalar_one()
        settled = await fixture.request(
            "POST", f"/trading/journal/{elsewhere}/resolve", {"outcome": "not_executed"}
        )
        assert settled["status"] == "resolved", settled
        await project()
        after = await card(waiting_card.id)
        assert (after.status, after.status_reason) == ("superseded", "operation_already_settled"), (
            after.status,
            after.status_reason,
        )
        print("PASS settling an operation elsewhere supersedes its waiting resolve card")

        # 8. The per-agent cap and expiry.
        expiring = {
            "kind": "trust_source",
            "source_kind": "feed_domain",
            "identifier": "cards-" + uuid4().hex[:8] + ".example.com",
        }
        waiting = [(await propose(expiring))["owner_action"]["id"]]
        for target in ("news_feed", "economic_calendar", "broker", "mcp_server"):
            waiting.append(
                (await propose({"kind": "connect_credential", "target": target}))["owner_action"][
                    "id"
                ]
            )
        assert (
            await propose_error(
                {"kind": "connect_credential", "target": "mcp_server", "service": "x"}
            )
            == "owner_action_limit"
        )
        async with db.sessions() as session, session.begin():
            row = await session.get(OwnerActionRow, waiting[0], with_for_update=True)
            assert row is not None
            row.expires_at = utcnow() - timedelta(seconds=1)
        shown = {row["id"]: row for row in await cards_in(thread["id"])}
        assert shown[waiting[0]]["status"] == "expired"
        status, late = await decide(waiting[0], {"decision": "confirm"})
        assert status == 200 and late["status"] == "expired" and late["status_reason"] == "expired"
        assert await trusted(expiring["identifier"]) is False
        # An expired card frees its slot and a new one can be proposed.
        fresh = await propose(expiring)
        assert fresh["owner_action"]["id"] != waiting[0] and not fresh["already_shown"]
        print("PASS at most five cards wait per agent; an expired card never acts")

        # Crash replay of the same tool call returns the same card, never a second one.
        call = "replayed-" + uuid4().hex
        status, _ = await decide(fresh["owner_action"]["id"], {"decision": "cancel"})
        assert status == 200
        first_call = await propose(expiring, call)
        second_call = await propose(expiring, call)
        assert first_call["owner_action"]["id"] == second_call["owner_action"]["id"]
        assert first_call["owner_action"]["id"] != fresh["owner_action"]["id"]
        print("PASS a replayed tool call returns the card it raised, never a second one")
    finally:
        await fixture.close(cleanup=False)


if __name__ == "__main__":
    asyncio.run(main())
