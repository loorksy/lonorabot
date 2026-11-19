"""Disposable PostgreSQL + real simulation adapter; no live broker or live money."""

import asyncio
import copy
from collections.abc import Awaitable, Callable
from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.brokers.simulation import SimulationBroker
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest, TradeResult
from lonora_db.schema import AgentRow, TradingAccountRow, TradingJournalRow
from lonora_db.trading_journal import persist_result
from lonora_db.transactions import SettingsRepository, execution_policy_key
from lonora_tools.loader import load_tools


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


async def main() -> None:
    fixture = await Fixture().open()
    db = fixture.runtime.db
    try:
        created = await fixture.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": "quality-fixture-" + uuid4().hex,
                "enabled": True,
            },
        )
        account_id = created["id"]
        symbol = "EURUSDm"
        await fixture.request(
            "POST",
            f"/trading/connections/{account_id}/simulation",
            {
                "snapshot": {
                    "balance": "10000",
                    "currency": "USD",
                    "instruments": [
                        {
                            "symbol": symbol,
                            "digits": 5,
                            "tick_size": "0.00001",
                            "volume_min": "0.1",
                            "volume_max": "100",
                            "volume_step": "0.1",
                        }
                    ],
                    "quotes": {
                        symbol: {
                            "symbol": symbol,
                            "bid": "1.10000",
                            "ask": "1.10020",
                            "observed_at": utcnow().isoformat(),
                            "source": "quality-fixture",
                        }
                    },
                    "positions": [
                        {
                            "id": "manual-ticket",
                            "symbol": symbol,
                            "side": "buy",
                            "volume": "0.1",
                            "open_price": "1.1",
                        }
                    ],
                }
            },
        )
        # Simulate an external MT5 position in the authoritative broker state,
        # independently of Lonora's operation ledger. Import API intentionally
        # initializes a clean demo account and does not import live positions.
        async with db.sessions() as session, session.begin():
            row = await session.get(TradingAccountRow, account_id, with_for_update=True)
            assert row is not None
            row.payload = {
                **row.payload,
                "positions": [
                    {
                        "id": "manual-ticket",
                        "symbol": symbol,
                        "side": "buy",
                        "volume": "0.1",
                        "open_price": "1.1",
                    }
                ],
            }
        services = fixture.runtime.services(fixture.owner)
        service = services.trading
        # Two concurrent closes of the one ticket opened outside Lonora: the account send
        # lock orders them, so the second is decided at its send boundary after the first.
        # The first is held inside the send lock until the second is reserved behind it, so
        # both are planned while the ticket is open.
        operations = [
            TradeRequest(
                account_id=account_id,
                symbol=symbol,
                action="close_position",
                position_id="manual-ticket",
            )
            for _ in range(2)
        ]
        await services.brokers.get(fixture.owner, account_id)
        cached = services.brokers.connections[account_id]
        gated = GatedSimulation(db, fixture.owner, account_id)
        services.brokers.connections[account_id] = (cached[0], gated)
        first = asyncio.create_task(service.execute(fixture.owner, operations[0]))
        await asyncio.wait_for(gated.waiting.wait(), 30)
        second = asyncio.create_task(service.execute(fixture.owner, operations[1]))
        for _ in range(300):
            async with db.sessions() as session:
                queued = await session.get(TradingJournalRow, operations[1].operation_id)
            if queued is not None and queued.status == "reserved":
                break
            await asyncio.sleep(0.05)
        else:
            raise AssertionError("the second close was never reserved behind the first")
        gated.release.set()
        outcomes = list(await asyncio.gather(first, second))
        services.brokers.connections[account_id] = cached
        assert sorted(result.status for result in outcomes) == ["confirmed", "failed"], [
            (item.status, item.code) for item in outcomes
        ]
        failed = next(item for item in outcomes if item.status == "failed")
        assert failed.code == "position_not_found"
        async with db.sessions() as session:
            row = await session.get(TradingJournalRow, failed.operation_id)
            assert row is not None
            assert row.result["details"]["send_state"] == "not_sent"
            observed = row.result["details"]["execution_evidence"]
            # Planned while the ticket was open; refused once the first close removed it.
            assert observed["planned"]["phase"] == "planned"
            assert observed["planned"]["counts"]["positions"] == 1
        repeated = await service.execute(
            fixture.owner, next(op for op in operations if op.operation_id == failed.operation_id)
        )
        assert repeated == failed
        print(
            "PASS two concurrent operations serialized: the second close of one ticket is refused at its send boundary once the first removed it; blocked result durable/idempotent"
        )
        close = next(item for item in outcomes if item.status == "confirmed")
        async with db.sessions() as session:
            row = await session.get(TradingJournalRow, close.operation_id)
            assert row
            original_evidence = copy.deepcopy(row.result["details"]["execution_evidence"])
            assert original_evidence["before_send"]["policy"]["quote_max_age_seconds"] == 60
            assert any(
                p["id"] == "manual-ticket"
                for p in original_evidence["before_send"]["snapshot"]["positions"]
            )
        # Later prices and reconciliation cannot replace what the executor knew.
        async with db.sessions() as session, session.begin():
            row = await session.get(TradingJournalRow, close.operation_id, with_for_update=True)
            assert row
            row.status = "ambiguous"
            assert await persist_result(
                session,
                close.operation_id,
                "confirmed",
                {
                    **close.model_dump(mode="json"),
                    "details": {"execution_evidence": {"forged": "later market"}},
                },
            )
            assert row.result["details"]["execution_evidence"] == original_evidence
        agent = await fixture.agent("Historical execution reader")
        async with db.sessions() as session, session.begin():
            row = await session.get(AgentRow, agent["id"])
            assert row
            row.role, row.trading_account_id, row.trading_symbol = "specialist", account_id, symbol
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        registry = load_tools()
        with patch.object(
            context.brokers,
            "get",
            AsyncMock(side_effect=AssertionError("Historical reads must not query today's broker")),
        ):
            record = await registry.execute(
                ToolCall(
                    id="past-read",
                    name="trade_record_read",
                    arguments={"operation_id": close.operation_id},
                ),
                context,
                scope="helper",
            )
            history = await registry.execute(
                ToolCall(id="past-list", name="trade_record_history", arguments={"limit": 10}),
                context,
                scope="helper",
            )
        # Trading records on owner accounts are shared operational records: a
        # fixed-market Agent reads the whole immutable evidence, not a projection.
        assert record["result"]["details"]["execution_evidence"] == original_evidence
        assert record["execution_authorized"] is False
        assert len(history["records"]) == 2 and all(
            item["symbol"] == symbol for item in history["records"]
        )
        # The terminal receipt retains immutable server attribution rather than
        # depending on a lease field that broker responses need not repeat.
        from lonora_contracts.execution_quality import PerformanceRead
        from lonora_trading.performance import performance_snapshot

        permission = await fixture.request("GET", f"/agents/{agent['id']}/permissions")
        # A root trading agent with no stored level starts at Ask me (W15-3).
        assert permission["effective_level"] == "supervised"
        await fixture.request(
            "PUT",
            f"/agents/{agent['id']}/permissions",
            {"level": "supervised", "expected_revision": permission["revision"]},
        )
        intent = ToolCall(
            id="approved-quality-attribution",
            name="trade_execute",
            arguments={
                "account_id": account_id,
                "symbol": symbol,
                "action": "buy",
                "volume": "0.1",
            },
        )
        pending = await registry.execute(intent, context)
        assert pending["_runtime_wait"]
        await fixture.request(
            "POST",
            f"/trading/approvals/{pending['approval_id']}/decision",
            {"decision": "approve"},
        )
        submitted = await registry.execute(intent, context)
        attributed = TradeResult.model_validate(submitted["results"][0])
        assert attributed.status == "confirmed"
        assert attributed.details["execution"]["agent_id"] == agent["id"]
        assert "lease" not in attributed.details
        summary = await performance_snapshot(
            db,
            fixture.owner,
            agent["id"],
            PerformanceRead(account_id=account_id, symbol=symbol),
        )
        assert summary["sample_count"] == 1
        assert summary["monetary_pnl"] is None and not summary["live_authority_granted"]
        print(
            "PASS blocked and executed historical evidence survives reconciliation; same read-only tool loop reads scoped receipts without broker access"
        )
        print("PASS owner manual position opened outside Lonora closes")

        # The quality gate at the send boundary reads the account's stored freshness bound
        # and records why it blocked: a quote 30 s old passes the broker preflight's window
        # but not a stored 5 s bound, so the operation is recorded blocked and never sent.
        async with db.sessions() as session, session.begin():
            await SettingsRepository().put(
                session,
                execution_policy_key(fixture.owner, account_id),
                {"quote_max_age_seconds": 5},
            )
            book = await session.get(TradingAccountRow, account_id, with_for_update=True)
            assert book is not None
            aged = (utcnow() - timedelta(seconds=30)).isoformat()
            book.payload = {
                **book.payload,
                "quotes": {
                    name: {**quote, "observed_at": aged}
                    for name, quote in book.payload["quotes"].items()
                },
            }
        stale = await service.execute(
            fixture.owner,
            TradeRequest(account_id=account_id, symbol=symbol, action="buy", volume=Decimal("0.1")),
        )
        assert stale.status == "failed" and stale.code == "market_quote_stale", stale
        async with db.sessions() as session:
            row = await session.get(TradingJournalRow, stale.operation_id)
            assert row is not None
            details = row.result["details"]
            assert details["send_state"] == "not_sent"
            assert details["execution_quality"]["state"] == "blocked"
            assert details["execution_quality"]["reasons"] == ["market_quote_stale"]
            before = details["execution_evidence"]["before_send"]
            assert before["policy"]["quote_max_age_seconds"] == 5
            book = await session.get(TradingAccountRow, account_id)
            assert book is not None
            assert stale.operation_id not in book.payload.get("operations", {})
        print(
            "PASS the send-boundary quality gate reads the stored freshness bound and records its block, never sent"
        )
    finally:
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
