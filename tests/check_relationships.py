"""Actual registry, broker history, lease and durable evidence integration."""

import asyncio
import json
from datetime import timedelta
from math import exp, sin
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.relationships import read_relationship
from lonora_db.schema import (
    AgentRow,
    MarketSnapshotRow,
    RunRow,
    TradingAccountRow,
    TradingJournalRow,
)
from lonora_db.trading_opportunities import owned_opportunity
from lonora_tools.loader import load_tools
from lonora_trading.opportunities import evidence_state
from sqlalchemy import delete, func, select


async def main():
    f = await Fixture().open()
    try:
        connection = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
            )
        )["id"]
        symbols = ["EURUSDm", "XAUUSD.raw", "US30.cash", "BTCUSD.pro"]
        now = utcnow()
        candles: dict[str, list[dict[str, Any]]] = {}
        for frame, minutes in (("1m", 1), ("15m", 15)):
            floor = now.replace(second=0, microsecond=0)
            floor -= timedelta(minutes=floor.minute % minutes)
            for symbol in symbols:
                price = 100.0
                bars: list[dict[str, Any]] = []
                for index in range(62):
                    price *= exp(0.001 * (sin(index * 1.7) + 0.4 * sin(index * 0.3)))
                    bars.append(
                        {
                            "symbol": symbol,
                            "timeframe": frame,
                            "time": (floor - timedelta(minutes=(61 - index) * minutes)).isoformat(),
                            "open": str(price),
                            "high": str(price),
                            "low": str(price),
                            "close": str(price),
                        }
                    )
                candles[symbol + ":" + frame] = bars
        await f.request(
            "POST",
            f"/trading/connections/{connection}/simulation",
            {
                "snapshot": {
                    "balance": "10000",
                    "currency": "USD",
                    "candles": candles,
                    "quotes": {
                        symbol: {
                            "symbol": symbol,
                            "bid": "100",
                            "ask": "101",
                            "observed_at": now.isoformat(),
                            "source": "scripted-relationship",
                        }
                        for symbol in symbols
                    },
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
                }
            },
        )
        agent = await f.agent("Relationship analyst")
        thread = await f.conversation(agent)
        context = await f.lease(await f.run(agent, thread))
        registry = load_tools()

        async def call(identifier: str, name: str, args: dict[str, Any]):
            return await registry.execute(
                ToolCall(id=identifier, name=name, arguments=args), context
            )

        saved = None
        for frame in ("1m", "15m"):
            for symbol in symbols[1:]:
                identifier = frame + symbol
                args = {
                    "account_id": connection,
                    "symbols": [symbols[0], symbol],
                    "timeframe": frame,
                }
                results = await asyncio.gather(
                    call(identifier, "market_relationship_record", args),
                    call(identifier, "market_relationship_record", args),
                )
                assert results[0] == results[1]
                saved = results[0]
                assert saved["state"] == "stable" and saved["sample_count"] == 30
                assert saved["symbols"] == args["symbols"] and "samples" not in saved
                assert saved["execution_authorized"] is saved["causal_claim"] is False
        assert saved
        args = {
            "account_id": connection,
            "symbol": symbols[0],
            "timeframe": "15m",
            "action": "BUY",
            "summary": "Broker evidence with measured cross-market support",
            "relationship_ids": [saved["id"]],
        }
        decision = await call("supported-decision", "market_decision_record", args)
        assert decision["action"] == "BUY" and not decision["execution_authorized"]
        assert decision["evidence"]["relationships"][0]["id"] == saved["id"]
        assert "samples" not in decision["evidence"]["relationships"][0]
        thesis = await call(
            "relationship-thesis",
            "market_opportunity_create",
            {
                "account_id": connection,
                "symbol": symbols[0],
                "timeframe": "15m",
                "setup_key": "measured-comparison",
                "definition": {
                    "direction": "BUY",
                    "rationale": "Recorded measured support",
                    "entry_condition": "Fresh account and broker evidence",
                    "invalidation_condition": "Support expires or changes",
                    "strategy_version": "scripted-relationship-v1",
                    "expires_at": (now + timedelta(hours=2)).isoformat(),
                },
                "supporting_decision_ids": [decision["id"]],
            },
        )
        async with f.runtime.db.sessions() as session:
            row = await owned_opportunity(session, f.owner, thesis["id"])
            codes, _ = await evidence_state(session, row, now + timedelta(hours=1))
            assert "relationship_evidence_unreliable" in codes
        print(
            "PASS forex, metal, index and crypto exact symbols across two horizons use real adapter history, shared leases and replay-safe measured evidence; association never grants execution"
        )

        unknown = await call(
            "unknown",
            "market_relationship_record",
            {
                "account_id": connection,
                "symbols": [symbols[0], "UNKNOWN.suffix"],
                "timeframe": "1m",
            },
        )
        assert not unknown["available"] and unknown["state"] == "unavailable"
        blocked = await call(
            "unavailable-decision",
            "market_decision_record",
            {**args, "relationship_ids": [unknown["id"]]},
        )
        assert (
            blocked["action"] == "WAIT"
            and "relationship_evidence_unreliable" in blocked["gate_codes"]
        )
        # Reading after a source correction returns the original metric, never hindsight.
        async with f.runtime.db.sessions() as session, session.begin():
            snapshot = await session.get(TradingAccountRow, connection)
            assert snapshot
            snapshot.payload = {**snapshot.payload, "candles": {}}
            await session.execute(
                delete(MarketSnapshotRow).where(
                    MarketSnapshotRow.connection_id == connection,
                    MarketSnapshotRow.timeframe != "",
                )
            )
        read = await call(
            "historical", "market_relationship_read", {"relationship_id": saved["id"]}
        )
        assert read == saved
        async with f.runtime.db.sessions() as session:
            full = await read_relationship(session, f.owner, saved["id"])
            assert len(full.samples) == 60
            try:
                await read_relationship(session, "another-owner", saved["id"])
            except LonoraError as error:
                assert error.code == "relationship_not_found"
            else:
                raise AssertionError("owner evidence leaked")
            assert await session.scalar(select(func.count()).select_from(TradingJournalRow)) == 0
        print(
            "PASS missing broker data forces WAIT, immutable aligned samples survive later source changes, owner isolation holds and no financial journal/mutation is created"
        )

        async with f.runtime.db.sessions() as session, session.begin():
            bound = await session.get(AgentRow, agent["id"])
            assert bound
            bound.role, bound.trading_account_id, bound.trading_symbol = (
                "specialist",
                connection,
                symbols[0],
            )
        assert (
            await call("scoped-read", "market_relationship_read", {"relationship_id": saved["id"]})
        )["id"] == saved["id"]
        try:
            await call(
                "wrong-scope",
                "market_relationship_record",
                {"account_id": connection, "symbols": symbols[1:3], "timeframe": "1m"},
            )
        except LonoraError as error:
            assert error.code == "agent_trading_symbol_mismatch"
        else:
            raise AssertionError("unrelated specialist scope allowed")
        with patch("lonora_tools.trading_decision.utcnow", return_value=now + timedelta(hours=1)):
            expired = await call("expired", "market_decision_record", args)
        assert (
            expired["action"] == "WAIT"
            and "relationship_evidence_unreliable" in expired["gate_codes"]
        )
        print(
            "PASS specialist comparisons require its own exact symbol/account; expired historical relationship evidence cannot justify a fresh recommendation"
        )
        phase = 0

        async def complete(
            _capability: Any, messages: list[ModelMessage], _tools: Any, **_kwargs: Any
        ):
            nonlocal phase
            phase += 1
            if phase == 1:
                reply = ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="runtime-relationship",
                            name="market_relationship_record",
                            arguments={
                                "account_id": connection,
                                "symbols": symbols[:2],
                                "timeframe": "15m",
                            },
                        )
                    ]
                )
            elif phase == 2:
                relationship = json.loads(messages[-1].content)
                assert relationship["ok"] is True and relationship["state"] == "unavailable"
                reply = ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="runtime-relationship-decision",
                            name="market_decision_record",
                            arguments={**args, "relationship_ids": [relationship["id"]]},
                        )
                    ]
                )
            else:
                outcome = json.loads(messages[-1].content)
                assert outcome["ok"] is True and outcome["action"] == "WAIT"
                reply = ModelReply(text="WAIT: relationship evidence is unavailable")
            return reply, ModelSelection(provider="openai", model="scripted-relationship-fixture")

        with patch.object(context.router, "complete", complete):
            await execute_run(context, registry, 120, 4)
        async with f.runtime.db.sessions() as session:
            run = await session.get(RunRow, context.lease.run_id)
            assert (
                run
                and run.status == "completed"
                and run.result == "WAIT: relationship evidence is unavailable"
            )
        print(
            "PASS same AgentRuntime/global router/tool loop consumes measured relationship state, persists gated WAIT and returns it to the conversation"
        )
        historical_context = await f.lease(await f.run(agent, thread))
        await f.request("DELETE", "/trading/connections/" + connection)
        retained = await registry.execute(
            ToolCall(
                id="retained-history",
                name="market_relationship_read",
                arguments={"relationship_id": saved["id"]},
            ),
            historical_context,
        )
        assert retained == saved
        print(
            "PASS owner-scoped historical evidence remains readable after broker connection removal without reconnecting or changing its source time"
        )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
