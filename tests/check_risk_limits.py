"""Monetary risk limits and the send boundary, on a disposable PostgreSQL database.

On a simulation account with one account-currency unit per tick per lot, the owner sets
each limit through the execution-policy route (a widening needs the passkey) and the owner
path is checked against every limit: per-trade risk at the stop, aggregate open risk
(positions, pending orders and unresolved operations), the daily loss (today's realized
deals plus floating P&L, cash flows excluded) and the free-margin floor; an approved agent
trade is checked against the per-trade limit. A blocked operation is recorded and never
sent; closing and cancelling stay admissible.

Then the send boundary itself: approved work that holds the account send lock but has not
passed its send boundary is decided there (a quote that goes stale meanwhile holds it,
recorded and never sent), and an operation whose acknowledgement is lost after the broker
applied it stays ambiguous and traceable and is confirmed from broker evidence with no
second broker call.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any, cast
from uuid import uuid4

from check_streaming import Fixture
from device_fixture import Device
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_db.schema import EventRow, TradingAccountRow, TradingJournalRow
from lonora_tools.loader import load_tools
from lonora_trading.reconciliation import reconcile_ambiguous
from sqlalchemy import delete, select

GOLD, EURO = "XAUUSD.r", "EURUSD.r"


class LostAcknowledgement(SimulationBroker):
    """The broker applies the order but its acknowledgement never arrives."""

    async def execute(
        self, request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        await super().execute(request, before_send)
        raise TimeoutError("explicit acknowledgement loss after the simulated effect")


class GatedSimulation(SimulationBroker):
    """Holds an operation inside the account send lock, before its send boundary."""

    def __init__(self, db: Any, owner_id: str, connection_id: str):
        super().__init__(db, owner_id, connection_id)
        self.waiting = asyncio.Event()
        self.release = asyncio.Event()

    async def execute(
        self, request: TradeRequest, before_send: Callable[[], Awaitable[None]] | None = None
    ) -> TradeResult:
        self.waiting.set()
        await self.release.wait()
        return await super().execute(request, before_send)


def instrument(symbol: str) -> dict[str, Any]:
    return {
        "symbol": symbol,
        "digits": 2,
        "tick_size": "0.01",
        "volume_min": "0.1",
        "volume_max": "10",
        "volume_step": "0.1",
    }


PRICES = {GOLD: ("2000.00", "2000.50"), EURO: ("100.00", "100.50")}


def quote(symbol: str) -> dict[str, Any]:
    bid, ask = PRICES[symbol]
    return {
        "symbol": symbol,
        "bid": bid,
        "ask": ask,
        "observed_at": utcnow().isoformat(),
        "source": "explicit-risk-fixture",
        # One account-currency unit per tick per lot: risk is easy to verify by hand.
        "loss_tick_value": "1",
        "profit_tick_value": "1",
        "tick_value_basis": "account_currency_per_lot",
    }


async def main() -> None:
    fixture = await Fixture().open()
    db = fixture.runtime.db
    connections: list[str] = []
    operations: list[str] = []
    try:

        async def connect(label: str) -> str:
            connection = await fixture.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": label + uuid4().hex, "enabled": True},
            )
            identifier = cast(str, connection["id"])
            connections.append(identifier)
            await fixture.request(
                "POST",
                f"/trading/connections/{identifier}/simulation",
                {
                    "snapshot": {
                        "currency": "USD",
                        "balance": "10000",
                        "instruments": [instrument(s) for s in (GOLD, EURO)],
                        "quotes": {s: quote(s) for s in (GOLD, EURO)},
                    }
                },
            )
            return identifier

        account = await connect("risk-")
        services = fixture.runtime.services(fixture.owner)
        service = services.trading
        await services.brokers.get(fixture.owner, account)

        async def edit_book(identifier: str, change: Callable[[dict[str, Any]], None]) -> None:
            async with db.sessions() as session, session.begin():
                row = await session.get(TradingAccountRow, identifier, with_for_update=True)
                assert row is not None
                payload = json.loads(json.dumps(row.payload))
                payload["quotes"] = {s: quote(s) for s in (GOLD, EURO)}
                change(payload)
                row.payload = payload

        async def refresh(identifier: str = account) -> None:
            await edit_book(identifier, lambda payload: None)

        def trade(
            action: str, symbol: str = GOLD, *, on: str = account, **fields: Any
        ) -> TradeRequest:
            operation = "risk-" + uuid4().hex
            operations.append(operation)
            return TradeRequest.model_validate(
                {
                    "account_id": on,
                    "operation_id": operation,
                    "action": action,
                    "symbol": symbol,
                    **fields,
                }
            )

        async def owner(request: TradeRequest) -> TradeResult:
            await refresh(request.account_id)
            return await service.execute(fixture.owner, request)

        async def journal(operation_id: str) -> TradingJournalRow:
            async with db.sessions() as session:
                row = await session.get(TradingJournalRow, operation_id)
                assert row is not None
                return row

        async def events(kind: str) -> list[dict[str, Any]]:
            async with db.sessions() as session:
                rows = await session.scalars(
                    select(EventRow)
                    .where(EventRow.owner_id == fixture.owner, EventRow.kind == kind)
                    .order_by(EventRow.cursor)
                )
                return [row.payload for row in rows]

        async def sent_to_broker(identifier: str = account) -> dict[str, Any]:
            async with db.sessions() as session:
                row = await session.get(TradingAccountRow, identifier)
                assert row is not None
                return dict(row.payload.get("operations", {}))

        # An approved agent trade runs in a Run the owner's message started.
        agent = await fixture.agent("Gold watcher", supervised=True)
        thread = await fixture.conversation(agent)
        sent = await fixture.request(
            "POST",
            f"/threads/{thread['id']}/messages",
            {
                "content": "Keep my gold trades inside the account limits",
                "client_nonce": "risk-" + uuid4().hex,
            },
        )
        run = {"id": sent["run_ids"][0], "agent_id": agent["id"], "thread_id": thread["id"]}
        context = await fixture.lease(run)
        registry = load_tools()

        async def approved(arguments: dict[str, Any], *, on: str = account) -> dict[str, Any]:
            call = ToolCall(
                id="card-" + uuid4().hex,
                name="trade_execute",
                arguments={"account_id": on, **arguments},
            )
            proposal = await registry.execute(call, context)
            if not proposal.get("_runtime_wait"):
                # The identical operation the owner already approved in this Run, which
                # reached the broker: its approval is reused, never asked twice (W15-3).
                assert proposal["results"], proposal
                return proposal
            await fixture.request(
                "POST",
                f"/trading/approvals/{proposal['approval_id']}/decision",
                {"decision": "approve"},
            )
            await refresh(on)
            outcome = await registry.execute(call, context)
            operations.extend(item["operation_id"] for item in outcome["results"])
            return outcome

        # Monetary limits on a clean account, from broker tick economics.
        risk = account
        policy_path = f"/trading/accounts/{risk}/execution-policy"
        wrong = await fixture.client.request(
            "PUT", "/api" + policy_path, json={"risk": {"currency": "EUR", "max_trade_risk": "50"}}
        )
        assert wrong.status_code == 409 and "risk_limit_currency_mismatch" in wrong.text
        unset = await fixture.request("GET", policy_path)
        assert all(
            unset["risk"][name] is None
            for name in ("max_trade_risk", "max_daily_loss", "max_open_risk", "min_free_margin")
        )
        status = await fixture.request("GET", f"/trading/accounts/{risk}/risk-status")
        assert status["state"] == "not_configured"

        signer: list[Device] = []

        async def store_policy(policy: dict[str, Any]) -> None:
            """Lowering or adding a limit is one request; replacing one (a removal) is a
            widening and goes through the passkey challenge bound to the exact policy."""
            response = await fixture.client.request("PUT", "/api" + policy_path, json=policy)
            if response.is_success:
                return
            assert response.status_code == 403, response.text
            assert "execution_policy_passkey_required" in response.text
            if not signer:
                signer.append(await Device.enroll(fixture))
            challenge = await fixture.request("POST", policy_path + "/challenge", policy)
            proof = signer[0].assertion(challenge, fixture.settings.allowed_origin)
            await fixture.request(
                "POST", policy_path + "/verify", {"policy": policy, "proof": proof}
            )

        async def limits(**values: str) -> None:
            await store_policy({"risk": {"currency": "USD", **values}})

        await limits(max_trade_risk="50")
        # Ask 2000.50 to a 1995.00 stop: 550 ticks * 1 per lot * 0.1 lot = 55 > 50.
        over = await owner(trade("buy", on=risk, volume="0.1", stop_loss="1995"))
        assert over.status == "failed" and over.code == "risk_trade_limit", over
        details = (await journal(over.operation_id)).result["details"]
        assert details["send_state"] == "not_sent"
        assert Decimal(details["risk_assessment"]["trade_risk"]) == 55
        assert details["admission_block"]["code"] == "risk_trade_limit"
        assert over.operation_id not in await sent_to_broker(risk)
        naked = await owner(trade("buy", on=risk, volume="0.1"))
        assert naked.status == "failed" and naked.code == "risk_stop_loss_required"
        within = await owner(trade("buy", on=risk, volume="0.1", stop_loss="1996"))
        assert within.status == "confirmed" and within.broker_id, within
        assessment = (await journal(within.operation_id)).result["details"]["risk_assessment"]
        assert assessment["state"] == "within_limits"
        assert Decimal(assessment["trade_risk"]) == 45
        agent_over = await approved(
            {"action": "buy", "symbol": GOLD, "volume": "0.1", "stop_loss": "1995"}, on=risk
        )
        assert agent_over["status"] == "failed" and agent_over["code"] == "risk_trade_limit"
        print(
            "PASS per-trade risk at the stop uses tick economics and blocks oversized or unprotected entries on the owner and agent paths, recording the evaluation"
        )

        await limits(max_open_risk="150")
        # Open: the gold position closes at the bid 2000.00 vs a 1996 stop = 400 ticks * 0.1 = 40.
        pending = await owner(
            trade("buy_limit", on=risk, volume="0.1", price="1990", stop_loss="1985")
        )
        assert pending.status == "confirmed" and pending.broker_id  # +50 = 90.
        unresolved = "risk-ambiguous-" + uuid4().hex
        operations.append(unresolved)
        ambiguous_request = TradeRequest(
            account_id=risk,
            operation_id=unresolved,
            action="buy",
            symbol=EURO,
            volume=Decimal(1),
            stop_loss=Decimal("100.00"),
        )
        async with db.sessions() as session, session.begin():
            session.add(
                TradingJournalRow(
                    operation_id=unresolved,
                    owner_id=fixture.owner,
                    account_id=risk,
                    request_hash="fixture",
                    request=ambiguous_request.model_dump(mode="json"),
                    status="ambiguous",
                    result={
                        "operation_id": unresolved,
                        "status": "ambiguous",
                        "code": "broker_result_ambiguous",
                        "details": {"send_state": "sent"},
                    },
                    submitted_at=utcnow(),
                    updated_at=utcnow(),
                )
            )
        # The ambiguous euro buy may have filled unseen: ask 100.50 to 100.00 = 50 ticks
        # * 1 lot = 50, so open risk is 140 and a 15-risk gold entry exceeds 150.
        crowded = await owner(trade("buy", on=risk, volume="0.1", stop_loss="1999"))
        assert crowded.status == "failed" and crowded.code == "risk_open_limit", crowded
        evaluated = (await journal(crowded.operation_id)).result["details"]["risk_assessment"]
        assert Decimal(evaluated["open_risk"]) == 155
        counted = {item["kind"] for item in evaluated["items"]}
        assert {"position", "order", "operation", "candidate"} <= counted, counted
        await fixture.request(
            "POST",
            f"/trading/journal/{unresolved}/resolve",
            {"outcome": "not_executed", "statement": "Checked the terminal: no euro position."},
        )
        fits = await owner(trade("buy", on=risk, volume="0.1", stop_loss="1999"))
        assert fits.status == "confirmed", fits
        unprotect = await owner(
            trade("modify_position", on=risk, position_id=within.broker_id, clear_stop_loss=True)
        )
        assert unprotect.status == "failed" and unprotect.code == "risk_open_unbounded"
        print(
            "PASS aggregate open risk counts positions, pending orders and unresolved operations conservatively, and blocks removing a stop"
        )

        await limits(max_daily_loss="100")
        day_start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)

        def losing_day(payload: dict[str, Any]) -> None:
            payload["history"] = [
                *payload.get("history", []),
                {"time": utcnow().isoformat(), "type": "DEAL_TYPE_SELL", "profit": "-80"},
                {
                    "time": (day_start - timedelta(hours=2)).isoformat(),
                    "type": "DEAL_TYPE_SELL",
                    "profit": "-500",
                },
                {"time": utcnow().isoformat(), "type": "DEAL_TYPE_BALANCE", "profit": "-1000"},
            ]
            for item in payload["positions"]:
                item["profit"] = "-30" if item["id"] == within.broker_id else "0"

        await edit_book(risk, losing_day)
        daily = await service.execute(
            fixture.owner, trade("buy", on=risk, volume="0.1", stop_loss="1999")
        )
        assert daily.status == "failed" and daily.code == "risk_daily_loss_limit", daily
        summary = (await journal(daily.operation_id)).result["details"]["risk_assessment"]["daily"]
        assert Decimal(summary["realized"]) == -80 and Decimal(summary["unrealized"]) == -30
        assert Decimal(summary["loss"]) == 110
        status = await fixture.request("GET", f"/trading/accounts/{risk}/risk-status")
        assert status["state"] == "blocked" and status["reasons"] == ["risk_daily_loss_limit"]
        exit_trade = await service.execute(
            fixture.owner, trade("close_position", on=risk, position_id=within.broker_id)
        )
        assert exit_trade.status == "confirmed", exit_trade
        recovered = await owner(trade("buy", on=risk, volume="0.1", stop_loss="1999"))
        assert recovered.status == "confirmed", recovered  # Realized -80 < 100 once closed.
        print(
            "PASS the daily loss limit counts today's realized deals plus floating P&L, excludes cash flows and yesterday, blocks new risk and still admits closing"
        )

        await limits(min_free_margin="20000")
        floor = await owner(trade("buy", on=risk, volume="0.1", stop_loss="1999"))
        assert floor.status == "failed" and floor.code == "risk_free_margin_floor"
        cancel = await owner(trade("cancel_order", on=risk, order_id=pending.broker_id))
        assert cancel.status == "confirmed", cancel
        assert (await events("trading.execution_policy_updated"))[-1]["account_id"] == risk
        await store_policy({})
        assert signer, "removing limits must have needed the passkey"
        cleared = await owner(trade("buy", on=risk, volume="0.1"))
        assert cleared.status == "confirmed"  # Unset limits are not enforced.
        print(
            "PASS the free-margin floor blocks new entries but not cancellations; clearing limits returns to not enforced"
        )

        # Approved work that holds the account send lock but has not passed its send boundary
        # is decided there: a quote that goes stale meanwhile holds it, recorded, never sent.
        gated = GatedSimulation(db, fixture.owner, risk)
        cached = services.brokers.connections[risk]
        call = ToolCall(
            id="queued-" + uuid4().hex,
            name="trade_execute",
            arguments={
                "account_id": risk,
                "action": "buy",
                "symbol": EURO,
                "volume": "0.2",
                "stop_loss": "99",
            },
        )
        proposal = await registry.execute(call, context)
        await fixture.request(
            "POST",
            f"/trading/approvals/{proposal['approval_id']}/decision",
            {"decision": "approve"},
        )
        await refresh(risk)
        services.brokers.connections[risk] = (cached[0], gated)
        queued = asyncio.create_task(registry.execute(call, context))
        waiting = asyncio.create_task(gated.waiting.wait())
        await asyncio.wait({queued, waiting}, timeout=30, return_when=asyncio.FIRST_COMPLETED)
        assert gated.waiting.is_set(), queued.result() if queued.done() else "not waiting"
        async with db.sessions() as session:
            waiting_row = await session.scalar(
                select(TradingJournalRow).where(
                    TradingJournalRow.owner_id == fixture.owner,
                    TradingJournalRow.status == "reserved",
                    TradingJournalRow.request["symbol"].as_string() == EURO,
                )
            )
            assert waiting_row is not None

        def stale(payload: dict[str, Any]) -> None:
            old = (utcnow() - timedelta(hours=1)).isoformat()
            payload["quotes"] = {s: {**q, "observed_at": old} for s, q in payload["quotes"].items()}

        await edit_book(risk, stale)
        gated.release.set()
        outcome = await asyncio.wait_for(queued, 60)
        services.brokers.connections[risk] = cached
        operations.extend(item["operation_id"] for item in outcome["results"])
        assert outcome["status"] == "failed" and outcome["code"] == "market_quote_stale", outcome
        row = await journal(outcome["operation_id"])
        assert row.operation_id == waiting_row.operation_id
        assert row.status == "failed" and row.result["details"]["send_state"] == "not_sent"
        assert outcome["operation_id"] not in await sent_to_broker(risk)
        print(
            "PASS approved work holding the send lock is decided at its send boundary: a quote gone stale meanwhile holds it, recorded and never sent"
        )

        # An operation interrupted after submission and before acknowledgement stays
        # traceable, and recovery establishes its outcome from broker evidence without
        # resending.
        services.brokers.connections[risk] = (
            cached[0],
            LostAcknowledgement(db, fixture.owner, risk),
        )
        interrupted = await approved(
            {"action": "buy", "symbol": GOLD, "volume": "0.3", "stop_loss": "1990"}, on=risk
        )
        services.brokers.connections[risk] = cached
        assert interrupted["status"] == "ambiguous", interrupted
        submitted_op = interrupted["operation_id"]
        row = await journal(submitted_op)
        assert row.status == "ambiguous"
        assert row.result["details"]["execution"]["send_authorized"] is True
        assert submitted_op in await sent_to_broker(risk)
        positions_before = len(await services.brokers.connections[risk][1].positions())
        await refresh(risk)
        # Recovery reads broker evidence and never calls the broker to execute again.
        simulation = services.brokers.connections[risk][1]
        executed: list[str] = []
        real_execute = simulation.execute

        async def counting_execute(request: TradeRequest, *args: Any, **kwargs: Any) -> TradeResult:
            executed.append(request.operation_id)
            return await real_execute(request, *args, **kwargs)

        simulation.execute = counting_execute  # type: ignore[method-assign]
        try:
            assert await reconcile_ambiguous(db, services.brokers) >= 1
        finally:
            simulation.execute = real_execute  # type: ignore[method-assign]
        assert executed == [], executed
        recovered_row = await journal(submitted_op)
        assert recovered_row.status == "confirmed", recovered_row.result
        assert len(await services.brokers.connections[risk][1].positions()) == positions_before
        print(
            "PASS an operation interrupted after submission stays traceable and recovery confirms it from broker evidence without resending"
        )
    finally:
        async with db.sessions() as session, session.begin():
            await session.execute(
                delete(TradingJournalRow).where(TradingJournalRow.operation_id.in_(operations))
            )
        for identifier in connections:
            await fixture.request("DELETE", "/trading/connections/" + identifier)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
