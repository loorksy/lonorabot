"""Disposable PG + canonical registry + simulation, with real approval/execution gates."""

import asyncio
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradingControl
from lonora_core.user_error import LonoraError
from lonora_db.schema import BrokerSessionRow, TradingAccountRow
from lonora_tools.loader import load_tools
from lonora_trading.controls import read_controls, save_controls


async def main() -> None:
    fixture = await Fixture().open()
    db = fixture.runtime.db
    original = await read_controls(db)
    connection = ""
    try:
        connection = (
            await fixture.request(
                "POST",
                "/trading/connections",
                {
                    "provider": "simulation",
                    "account_id": uuid4().hex,
                    "enabled": True,
                },
            )
        )["id"]
        now = utcnow()
        symbols = ("EURUSDm", "XAUUSDm", "US30.cash", "BTCUSD.pro")
        frames = ("1m", "15m", "1h", "4h")
        await fixture.request(
            "POST",
            f"/trading/connections/{connection}/simulation",
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
                        for symbol in symbols
                    ],
                    "quotes": {
                        symbol: {
                            "symbol": symbol,
                            "bid": "100",
                            "ask": "101",
                            "observed_at": now.isoformat(),
                            "source": "decision-readiness-fixture",
                        }
                        for symbol in symbols
                    },
                    "candles": {
                        symbol + ":" + frame: [
                            {
                                "symbol": symbol,
                                "timeframe": frame,
                                "time": (now - timedelta(minutes=3 - i)).isoformat(),
                                "open": "99",
                                "high": "102",
                                "low": "98",
                                "close": "100",
                            }
                            for i in range(3)
                        ]
                        for symbol, frame in zip(symbols, frames, strict=True)
                    },
                }
            },
        )
        await save_controls(db, TradingControl(enabled=True))
        agent = await fixture.agent("Readiness analyst")
        context = await fixture.lease(await fixture.run(agent, await fixture.conversation(agent)))
        registry = load_tools()
        broker = await context.brokers.get(fixture.owner, connection)

        def arguments(symbol: str, frame: str) -> dict[str, Any]:
            return {
                "account_id": connection,
                "symbol": symbol,
                "timeframe": frame,
                "action": "BUY",
                "summary": "The independently observed bid is above the explicit structural level; execution remains separately gated.",
                "market_view": {
                    "bias": "BULLISH",
                    "supporting_condition": {
                        "id": "structural-level",
                        "kind": "level",
                        "level": "99",
                    },
                },
                "entry_condition": {"id": "entry-level", "kind": "level", "level": "99"},
            }

        async def record(identity: str, symbol: str, frame: str) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(
                    id=identity, name="market_decision_record", arguments=arguments(symbol, frame)
                ),
                context,
            )

        records: list[dict[str, Any]] = []
        for symbol, frame in zip(symbols, frames, strict=True):
            result = await record(symbol, symbol, frame)
            readiness = result["readiness"]
            assert readiness["market_assessment"]["bias"] == "BULLISH"
            assert readiness["entry_readiness"]["state"] == "CONFIRMED"
            assert readiness["execution_readiness"]["state"] == "REVALIDATION_REQUIRED"
            assert result["execution_authorized"] is False
            records.append(result)
        print(
            "PASS canonical decision tool independently inspects forex/metal/index/crypto and four timeframes"
        )

        quote = await broker.quote(symbols[0])
        retry = AsyncMock(side_effect=[LonoraError("broker_connection_timeout", 503), quote])
        with patch.object(broker, "quote", retry):
            recovered = await record("recover", symbols[0], frames[0])
        assert retry.await_count == 2
        assert recovered["evidence"]["recovered_read_codes"] == ["quote:broker_connection_timeout"]
        assert recovered["readiness"]["market_assessment"]["bias"] == "BULLISH"
        with patch.object(
            broker, "orders", AsyncMock(side_effect=LonoraError("broker_orders_unavailable", 503))
        ):
            unrelated = await record("orders-unavailable", symbols[0], frames[0])
        assert unrelated["action"] == "BUY"
        assert unrelated["readiness"]["market_assessment"]["bias"] == "BULLISH"
        assert unrelated["readiness"]["entry_readiness"]["state"] == "CONFIRMED"
        assert unrelated["readiness"]["execution_readiness"]["state"] == "BLOCKED"
        print(
            "PASS bounded safe read recovery and independent market interpretation survive unrelated order failure"
        )

        async with db.sessions() as session, session.begin():
            row = await session.get(BrokerSessionRow, connection, with_for_update=True)
            assert row
            row.state = {**row.state, "broker_recovery": {"status": "reconciling"}}
        reconciling = await record("reconciling", symbols[0], frames[0])
        readiness = reconciling["readiness"]
        assert readiness["market_assessment"]["bias"] == "BULLISH"
        assert readiness["execution_readiness"]["reason_codes"] == [
            "broker_reconciliation_required"
        ]
        before = await broker.positions()
        command = ToolCall(
            id="entry-after-analysis",
            name="trade_execute",
            arguments={
                "account_id": connection,
                "symbol": symbols[0],
                "action": "buy",
                "volume": "0.01",
            },
        )
        proposal = await registry.execute(command, context)
        assert proposal["_runtime_wait"] and await broker.positions() == before
        await fixture.request(
            "POST",
            f"/trading/approvals/{proposal['approval_id']}/decision",
            {"decision": "approve"},
        )
        blocked = await registry.execute(command, context)
        assert (
            blocked["status"] == "failed" and blocked["code"] == "broker_reconciliation_required"
        ), blocked
        assert await broker.positions() == before
        print(
            "PASS supported opinion + confirmed trigger + actual owner approval cannot bypass broker reconciliation; no trade opened"
        )

        with patch.object(
            context.brokers,
            "get",
            AsyncMock(
                side_effect=AssertionError("Historical readiness cannot fetch new market data")
            ),
        ):
            historical = await registry.execute(
                ToolCall(
                    id="historical",
                    name="market_decision_read",
                    arguments={"decision_id": reconciling["id"]},
                ),
                context,
            )
        assert historical == reconciling
        history = await registry.execute(
            ToolCall(
                id="history", name="market_decision_history", arguments={"account_id": connection}
            ),
            context,
        )
        assert any(value["readiness"]["market_bias"] == "BULLISH" for value in history["decisions"])
        async with db.sessions() as session, session.begin():
            row = await session.get(TradingAccountRow, connection, with_for_update=True)
            assert row
            quotes = dict(row.payload["quotes"])
            quotes[symbols[0]] = {
                **quotes[symbols[0]],
                "observed_at": (now - timedelta(hours=1)).isoformat(),
            }
            row.payload = {**row.payload, "quotes": quotes}
        stale = await record("stale", symbols[0], frames[0])
        assert stale["readiness"]["market_assessment"]["bias"] == "INSUFFICIENT_EVIDENCE"
        assert stale["readiness"]["entry_readiness"]["state"] == "INSUFFICIENT_EVIDENCE"
        unknown = await record("unknown", "NOT_A_BROKER_SYMBOL", "1m")
        assert unknown["readiness"]["market_assessment"]["bias"] == "INSUFFICIENT_EVIDENCE"
        assert unknown["readiness"]["execution_readiness"]["state"] == "BLOCKED"
        print(
            "PASS immutable readiness replay and compact history; stale/unknown markets never manufacture bias or entry"
        )
    finally:
        await save_controls(db, original)
        if connection:
            await fixture.client.delete(f"/api/trading/connections/{connection}")
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
