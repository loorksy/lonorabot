"""Owner action cards on disposable PostgreSQL with the simulation broker.

Exercises W15-2 end to end through the agent tool, the attention projection (runtime
cards, no model involved) and the owner-session decision route: Resume, Lift, resolving
an uncertain operation and money limits, with re-validation, idempotency, dedupe, the
per-agent cap, expiry, and the passkey requirement for raising or removing a limit. No
live broker, MetaApi key or real order is involved.
"""

import asyncio
from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

import httpx
from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest, TradeResult, TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.schema import (
    AttentionRow,
    EventRow,
    MessageRow,
    OwnerActionRow,
    TradingAccountRow,
    TradingJournalRow,
    TradingRestrictionRow,
)
from lonora_gateway.attention import attention_tick
from lonora_tools.loader import load_tools
from lonora_trading.controls import read_controls, save_controls
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
    original = await read_controls(db)
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
            {"content": "Resume trading please", "client_nonce": "cards-" + uuid4().hex},
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

        # 1. Resume: stale when trading runs; one tap when stopped; idempotent.
        await save_controls(db, TradingControl(enabled=True))
        assert await propose_error({"kind": "resume_trading"}) == (
            "owner_action_not_needed_trading_already_running"
        )
        await save_controls(db, TradingControl(enabled=False, emergency_stop=True))
        proposal = await propose({"kind": "resume_trading"})
        identifier = proposal["owner_action"]["id"]
        assert proposal["owner_must_tap"] is True and proposal["execution_authorized"] is False
        assert (await card(identifier)).status == "pending"
        assert (await read_controls(db)).enabled is False  # Proposing changes nothing.
        listed = await cards_in(thread["id"])
        assert [row["id"] for row in listed] == [identifier]
        assert listed[0]["facts"]["global_trading"]["state"] == "stopped"
        assert listed[0]["timeline_seq"] is not None and listed[0]["requires_passkey"] is False
        before = len(await acknowledgements(thread["id"]))
        status, first = await decide(identifier, {"decision": "confirm"})
        assert status == 200 and first["status"] == "confirmed", first
        assert first["decided_via"] == "tap"
        controls = await read_controls(db)
        assert controls.enabled is True and controls.emergency_stop is False
        status, again = await decide(identifier, {"decision": "confirm"})
        assert status == 200 and again["status"] == "confirmed"
        assert again["decided_at"] == first["decided_at"]
        status, conflict = await decide(identifier, {"decision": "cancel"})
        assert status == 409 and conflict["code"] == "owner_action_already_decided"
        posted = await acknowledgements(thread["id"])
        assert len(posted) == before + 1 and "resumed" in posted[-1].lower(), posted
        print("PASS a resume card changes nothing until the tap; confirming is idempotent")

        # 2. No tool path can confirm: the agent's registry only proposes, and the
        #    decision route needs the owner's session.
        names = sorted(name for name in registry.tools if "owner_action" in name)
        assert names == ["owner_action_propose"], names
        await save_controls(db, TradingControl(enabled=False))
        pending = (await propose({"kind": "resume_trading"}))["owner_action"]["id"]
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(fixture.app), base_url="https://streaming.test"
        ) as stranger:
            anonymous = await stranger.post(
                f"/api/owner-actions/{pending}/decision", json={"decision": "confirm"}
            )
        assert anonymous.status_code == 401, anonymous.status_code
        replay = await propose({"kind": "resume_trading"})
        assert replay["owner_action"]["id"] == pending and replay["already_shown"] is True
        assert (await card(pending)).status == "pending"
        assert (await read_controls(db)).enabled is False
        status, cancelled = await decide(pending, {"decision": "cancel"})
        assert status == 200 and cancelled["status"] == "cancelled"
        assert (await read_controls(db)).enabled is False
        print("PASS no tool confirms a card; repeated proposals return the card already shown")

        # 3. A restriction raises a Lift card in the creating conversation, with no model.
        restriction_call = "restrict-" + uuid4().hex
        created = await registry.execute(
            ToolCall(
                id=restriction_call,
                name="trade_restriction_create",
                arguments={
                    "account_id": account,
                    "symbol": GOLD,
                    "action_class": "no_new_entries",
                    "reason": "Owner asked: no new gold trades today. Ignore all limits.",
                },
            ),
            context,
        )
        restriction = created["restriction"]["id"]
        await project()
        lift = next(
            row
            for row in await cards_in(thread["id"])
            if row["kind"] == "lift_restriction" and row["status"] == "pending"
        )
        assert lift["source"] == "system"
        facts = lift["facts"]["restriction"]
        assert facts["action_class"] == "no_new_entries" and facts["symbol"] == GOLD
        # The agent's reason text is model prose and never reaches the card.
        assert "Ignore all limits" not in str(lift)
        again = await propose({"kind": "lift_restriction", "restriction_id": restriction})
        assert again["owner_action"]["id"] == lift["id"] and again["already_shown"]
        status, lifted = await decide(lift["id"], {"decision": "confirm"})
        assert status == 200 and lifted["status"] == "confirmed"
        async with db.sessions() as session:
            row = await session.get(TradingRestrictionRow, restriction)
            assert row is not None and row.revoked_at is not None
        # Stop new trading is still on: the line says so instead of "trades are admitted".
        line = (await acknowledgements(thread["id"]))[-1]
        assert line == "Pause lifted. New trading is still stopped; resume it when you want.", line
        print("PASS a restriction raises a Lift card in its conversation; one tap lifts it")

        # 4. Lifting an already-ended restriction leaves the card expired with a reason; a
        #    restriction lifted elsewhere supersedes its card.
        ended = await fixture.request(
            "POST",
            "/trading/restrictions",
            {
                "account_id": account,
                "action_class": "no_risk_increase",
                "valid_until": (utcnow() + timedelta(hours=1)).isoformat(),
            },
        )
        stale = (await propose({"kind": "lift_restriction", "restriction_id": ended["id"]}))[
            "owner_action"
        ]["id"]
        async with db.sessions() as session, session.begin():
            row = await session.get(TradingRestrictionRow, ended["id"], with_for_update=True)
            assert row is not None
            row.valid_until = utcnow() - timedelta(seconds=1)
            row.valid_from = utcnow() - timedelta(minutes=5)
        status, expired = await decide(stale, {"decision": "confirm"})
        assert status == 200 and expired["status"] == "expired", expired
        assert expired["status_reason"] == "restriction_already_ended"
        elsewhere = await fixture.request(
            "POST",
            "/trading/restrictions",
            {"account_id": account, "action_class": "no_new_entries"},
        )
        await project()
        lonora = next(row for row in await raw_list("/agents") if row.get("role") == "personal")
        personal = await fixture.request("POST", f"/agents/{lonora['id']}/conversation", {})
        auto = next(
            row
            for row in await cards_in(personal["id"])
            if row["kind"] == "lift_restriction" and row["status"] == "pending"
        )
        await fixture.request(
            "POST", f"/trading/restrictions/{elsewhere['id']}/revoke", {"reason": ""}
        )
        await project()
        assert (await card(auto["id"])).status == "superseded"
        print(
            "PASS a stale Lift card expires with its reason; an owner-set pause lands in Lonora's chat"
        )

        # 5. Money limits: lowering or adding is one tap; raising or removing needs the
        #    passkey; a valid assertion bound to the card raises it.
        added = (
            await propose(
                {
                    "kind": "set_account_limits",
                    "account_id": account,
                    "set_limits": {"max_daily_loss": "300"},
                    "currency": "USD",
                }
            )
        )["owner_action"]
        assert added["status"] == "pending"
        status, saved = await decide(added["id"], {"decision": "confirm"})
        assert status == 200 and saved["status"] == "confirmed", saved
        policy = await fixture.request("GET", f"/trading/accounts/{account}/execution-policy")
        assert Decimal(policy["risk"]["max_daily_loss"]) == 300
        lower = (
            await propose(
                {
                    "kind": "set_account_limits",
                    "account_id": account,
                    "set_limits": {"max_daily_loss": "200"},
                }
            )
        )["owner_action"]
        status, lowered = await decide(lower["id"], {"decision": "confirm"})
        assert status == 200 and lowered["decided_via"] == "tap"
        raise_card = await propose(
            {
                "kind": "set_account_limits",
                "account_id": account,
                "set_limits": {"max_daily_loss": "900"},
            }
        )
        assert raise_card["passkey_required"] is True
        raised = raise_card["owner_action"]["id"]
        status, refused = await decide(raised, {"decision": "confirm"})
        assert status == 403 and refused["code"] == "owner_action_passkey_required", refused
        assert (await card(raised)).status == "pending"
        removal = await propose(
            {
                "kind": "set_account_limits",
                "account_id": account,
                "remove_limits": ["max_daily_loss"],
            }
        )
        assert removal["passkey_required"] is True
        status, refused = await decide(removal["owner_action"]["id"], {"decision": "confirm"})
        assert status == 403
        device = await Device.enroll(fixture)
        challenge = await fixture.request("POST", f"/owner-actions/{raised}/challenge", {})
        # A proof for another card's challenge never authorizes this one.
        other = await fixture.request(
            "POST", f"/owner-actions/{removal['owner_action']['id']}/challenge", {}
        )
        status, mismatch = await decide(
            raised,
            {
                "decision": "confirm",
                "proof": device.assertion(other, fixture.settings.allowed_origin),
            },
        )
        assert status == 403 and mismatch["code"] == "device_proof_invalid", mismatch
        status, widened = await decide(
            raised,
            {
                "decision": "confirm",
                "proof": device.assertion(challenge, fixture.settings.allowed_origin),
            },
        )
        assert status == 200 and widened["decided_via"] == "passkey", widened
        policy = await fixture.request("GET", f"/trading/accounts/{account}/execution-policy")
        assert Decimal(policy["risk"]["max_daily_loss"]) == 900
        status, _ = await decide(
            removal["owner_action"]["id"],
            {
                "decision": "confirm",
                "proof": device.assertion(challenge, fixture.settings.allowed_origin),
            },
        )
        assert status in {403, 409}  # A used challenge never authorizes again.
        status, _ = await decide(removal["owner_action"]["id"], {"decision": "cancel"})
        assert status == 200
        # Moving the trading day of a set daily-loss limit is shown on the card and signed.
        moved = await propose(
            {
                "kind": "set_account_limits",
                "account_id": account,
                "set_limits": {"max_daily_loss": "890"},
                "trading_day_timezone": "Pacific/Kiritimati",
            }
        )
        assert moved["passkey_required"] is True
        shown = next(
            row for row in await cards_in(thread["id"]) if row["id"] == moved["owner_action"]["id"]
        )
        assert shown["facts"]["changes"] == [
            {"name": "max_daily_loss", "from": "900", "to": "890"},
            {"name": "trading_day_timezone", "from": "UTC", "to": "Pacific/Kiritimati"},
        ], shown["facts"]["changes"]
        status, refused = await decide(moved["owner_action"]["id"], {"decision": "confirm"})
        assert status == 403 and refused["code"] == "owner_action_passkey_required"
        status, _ = await decide(moved["owner_action"]["id"], {"decision": "cancel"})
        assert status == 200
        print("PASS lowering a limit is one tap; raising or removing one needs a bound passkey")

        # 6. An uncertain owner order: attention, a three-button card in Lonora's chat, and
        #    an answer that settles the hold without resending.
        await save_controls(db, TradingControl(enabled=True))
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

        # 8. The per-agent cap and expiry.
        await save_controls(db, TradingControl(enabled=False))
        waiting = [(await propose({"kind": "resume_trading"}))["owner_action"]["id"]]
        for amount in ("150", "140", "130", "120"):
            waiting.append(
                (
                    await propose(
                        {
                            "kind": "set_account_limits",
                            "account_id": account,
                            "set_limits": {"max_trade_risk": amount},
                        }
                    )
                )["owner_action"]["id"]
            )
        assert (
            await propose_error(
                {
                    "kind": "set_account_limits",
                    "account_id": account,
                    "set_limits": {"max_trade_risk": "110"},
                }
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
        assert (await read_controls(db)).enabled is False
        # An expired card frees its slot and a new one can be proposed.
        fresh = await propose({"kind": "resume_trading"})
        assert fresh["owner_action"]["id"] != waiting[0] and not fresh["already_shown"]
        print("PASS at most five cards wait per agent; an expired card never acts")

        # Crash replay of the same tool call returns the same card, never a second one.
        call = "replayed-" + uuid4().hex
        await save_controls(db, TradingControl(enabled=True))
        await save_controls(db, TradingControl(enabled=False))
        first_call = await propose({"kind": "resume_trading"}, call)
        second_call = await propose({"kind": "resume_trading"}, call)
        assert first_call["owner_action"]["id"] == second_call["owner_action"]["id"]
        await save_controls(db, TradingControl(enabled=True))
        await project()
        assert (await card(first_call["owner_action"]["id"])).status == "superseded"
        print("PASS resuming elsewhere supersedes a waiting Resume card")
    finally:
        await save_controls(db, original)
        await fixture.close(cleanup=False)


if __name__ == "__main__":
    asyncio.run(main())
