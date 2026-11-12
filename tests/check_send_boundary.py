"""The send boundary, on a disposable PostgreSQL database.

Approved work that holds the account send lock but has not passed its send boundary is
decided there (a quote that goes stale meanwhile holds it, recorded and never sent), and an
operation whose acknowledgement is lost after the broker applied it stays ambiguous and
traceable and is confirmed from broker evidence with no second broker call.
"""

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import timedelta
from typing import Any, cast
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_db.schema import TradingAccountRow, TradingJournalRow
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
        "source": "explicit-send-boundary-fixture",
    }


async def main() -> None:
    fixture = await Fixture().open()
    db = fixture.runtime.db
    connections: list[str] = []
    operations: list[str] = []
    try:
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": "boundary-" + uuid4().hex, "enabled": True},
        )
        account = cast(str, connection["id"])
        connections.append(account)
        await fixture.request(
            "POST",
            f"/trading/connections/{account}/simulation",
            {
                "snapshot": {
                    "currency": "USD",
                    "balance": "10000",
                    "instruments": [instrument(s) for s in (GOLD, EURO)],
                    "quotes": {s: quote(s) for s in (GOLD, EURO)},
                }
            },
        )
        services = fixture.runtime.services(fixture.owner)
        await services.brokers.get(fixture.owner, account)

        async def edit_book(change: Callable[[dict[str, Any]], None]) -> None:
            async with db.sessions() as session, session.begin():
                row = await session.get(TradingAccountRow, account, with_for_update=True)
                assert row is not None
                payload = json.loads(json.dumps(row.payload))
                payload["quotes"] = {s: quote(s) for s in (GOLD, EURO)}
                change(payload)
                row.payload = payload

        async def refresh() -> None:
            await edit_book(lambda payload: None)

        async def journal(operation_id: str) -> TradingJournalRow:
            async with db.sessions() as session:
                row = await session.get(TradingJournalRow, operation_id)
                assert row is not None
                return row

        async def sent_to_broker() -> dict[str, Any]:
            async with db.sessions() as session:
                row = await session.get(TradingAccountRow, account)
                assert row is not None
                return dict(row.payload.get("operations", {}))

        # An approved agent trade runs in a Run the owner's message started.
        agent = await fixture.agent("Gold watcher", supervised=True)
        thread = await fixture.conversation(agent)
        sent = await fixture.request(
            "POST",
            f"/threads/{thread['id']}/messages",
            {
                "content": "Trade gold on this account when I approve it",
                "client_nonce": "boundary-" + uuid4().hex,
            },
        )
        run = {"id": sent["run_ids"][0], "agent_id": agent["id"], "thread_id": thread["id"]}
        context = await fixture.lease(run)
        registry = load_tools()

        async def approved(arguments: dict[str, Any]) -> dict[str, Any]:
            call = ToolCall(
                id="card-" + uuid4().hex,
                name="trade_execute",
                arguments={"account_id": account, **arguments},
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
            await refresh()
            outcome = await registry.execute(call, context)
            operations.extend(item["operation_id"] for item in outcome["results"])
            return outcome

        # Approved work that holds the account send lock but has not passed its send boundary
        # is decided there: a quote that goes stale meanwhile holds it, recorded, never sent.
        gated = GatedSimulation(db, fixture.owner, account)
        cached = services.brokers.connections[account]
        call = ToolCall(
            id="queued-" + uuid4().hex,
            name="trade_execute",
            arguments={
                "account_id": account,
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
        await refresh()
        services.brokers.connections[account] = (cached[0], gated)
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

        await edit_book(stale)
        gated.release.set()
        outcome = await asyncio.wait_for(queued, 60)
        services.brokers.connections[account] = cached
        operations.extend(item["operation_id"] for item in outcome["results"])
        assert outcome["status"] == "failed" and outcome["code"] == "market_quote_stale", outcome
        row = await journal(outcome["operation_id"])
        assert row.operation_id == waiting_row.operation_id
        assert row.status == "failed" and row.result["details"]["send_state"] == "not_sent"
        assert outcome["operation_id"] not in await sent_to_broker()
        print(
            "PASS approved work holding the send lock is decided at its send boundary: a quote gone stale meanwhile holds it, recorded and never sent"
        )

        # An operation interrupted after submission and before acknowledgement stays
        # traceable, and recovery establishes its outcome from broker evidence without
        # resending.
        services.brokers.connections[account] = (
            cached[0],
            LostAcknowledgement(db, fixture.owner, account),
        )
        interrupted = await approved(
            {"action": "buy", "symbol": GOLD, "volume": "0.3", "stop_loss": "1990"}
        )
        services.brokers.connections[account] = cached
        assert interrupted["status"] == "ambiguous", interrupted
        submitted_op = interrupted["operation_id"]
        row = await journal(submitted_op)
        assert row.status == "ambiguous"
        assert row.result["details"]["execution"]["send_authorized"] is True
        assert submitted_op in await sent_to_broker()
        positions_before = len(await services.brokers.connections[account][1].positions())
        await refresh()
        # Recovery reads broker evidence and never calls the broker to execute again.
        simulation = services.brokers.connections[account][1]
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
        assert len(await services.brokers.connections[account][1].positions()) == positions_before
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
