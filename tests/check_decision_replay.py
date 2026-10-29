"""Actual simulation/API/tool-loop admission; no live broker or model dependency."""

import asyncio
import json
from datetime import timedelta
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.context.decisions import decision_context
from lonora_agent.executor import execute_run
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.schema import AgentRow, EventRow, RunRow, TradingAccountRow
from lonora_db.trading_decisions import read_decision
from lonora_tools.loader import load_tools
from sqlalchemy import select


async def main() -> None:
    f = await Fixture().open()
    connection = ""
    try:
        connection = (
            await f.request(
                "POST",
                "/trading/connections",
                {
                    "provider": "simulation",
                    "account_id": uuid4().hex,
                    "enabled": True,
                },
            )
        )["id"]
        symbols = ("EURUSDm", "XAUUSDm", "US30.cash", "BTCUSD.pro")
        frames = ("5m", "15m", "1h", "4h")
        now = utcnow()
        await f.request(
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
                            "source": "explicit-decision-fixture",
                        }
                        for symbol in symbols
                    },
                    "candles": {
                        symbol + ":" + frame: [
                            {
                                "symbol": symbol,
                                "timeframe": frame,
                                "time": (now - timedelta(minutes=10 - i)).isoformat(),
                                "open": "100",
                                "high": "102",
                                "low": "99",
                                "close": "101",
                            }
                            for i in range(10)
                        ]
                        for symbol, frame in zip(symbols, frames, strict=True)
                    },
                }
            },
        )
        agent = await f.agent("Evidence analyst")
        thread = await f.conversation(agent)
        context = await f.lease(await f.run(agent, thread))
        registry = load_tools()

        async def call(identifier: str, name: str, args: dict[str, Any]) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(id=identifier, name=name, arguments=args), context
            )

        records: list[dict[str, Any]] = []
        for symbol, frame in zip(symbols, frames, strict=True):
            args = {
                "account_id": connection,
                "symbol": symbol,
                "timeframe": frame,
                "action": "BUY",
                "summary": "Recorded user-visible fixture rationale",
            }
            saved = await call(symbol, "market_decision_record", args)
            assert saved["action"] == "BUY" and saved["execution_authorized"] is False
            assert saved["evidence"]["quote"]["symbol"] == symbol
            assert saved == await call(symbol, "market_decision_record", args)
            records.append(saved)
        try:
            await call(
                symbols[0],
                "market_decision_record",
                {
                    "account_id": connection,
                    "symbol": symbols[0],
                    "timeframe": frames[0],
                    "action": "BUY",
                    "summary": "Changed intent on the same call",
                },
            )
        except LonoraError as error:
            assert error.code == "decision_intent_conflict"
        else:
            raise AssertionError("Same operation rewrote historical decision")
        async with f.runtime.db.sessions() as session:
            events = list(
                await session.scalars(
                    select(EventRow).where(
                        EventRow.run_id == context.lease.run_id,
                        EventRow.kind == "trading.decision_recorded",
                    )
                )
            )
            assert len(events) == 4
            seed = await decision_context(session, f.owner, agent["id"])
            assert len(seed) < 4000 and "historical" in seed.lower()
        print(
            "PASS exact forex/metal/index/crypto and multiple frames preserve one decision per tool identity"
        )

        async with f.runtime.db.sessions() as session, session.begin():
            account = await session.get(TradingAccountRow, connection, with_for_update=True)
            assert account
            quotes = dict(account.payload["quotes"])
            quotes[symbols[0]] = {
                **quotes[symbols[0]],
                "bid": "105",
                "ask": "106",
                "observed_at": (now - timedelta(hours=1)).isoformat(),
            }
            account.payload = {**account.payload, "quotes": quotes}
        changed = await call(
            "later-wait",
            "market_decision_record",
            {
                "account_id": connection,
                "symbol": symbols[0],
                "timeframe": frames[0],
                "action": "BUY",
                "summary": "Requested direction, subject to actual data health",
            },
        )
        assert changed["action"] == "BUY" and any("stale" in code for code in changed["gate_codes"])
        assert changed["readiness"]["execution_readiness"]["state"] == "BLOCKED"
        with patch.object(
            context.brokers,
            "get",
            AsyncMock(
                side_effect=AssertionError("Historical reads must not fetch today's broker data")
            ),
        ):
            historical = await call(
                "history", "market_decision_read", {"decision_id": records[0]["id"]}
            )
            assert historical["evidence"]["quote"]["bid"] == "100"
            changes = await call(
                "changes",
                "market_decision_compare",
                {"earlier_id": records[0]["id"], "later_id": changed["id"]},
            )
            assert "action" not in changes["changes"]
            assert "readiness" in changes["changes"]
            assert changes["changes"]["bid"] == {"before": "100", "after": "105"}
            recent = await call("recent", "market_decision_history", {"account_id": connection})
            assert all(
                "evidence" not in item and "evidence_id" in item for item in recent["decisions"]
            )
        print(
            "PASS stale evidence blocks execution while preserving model intent; immutable replay/deltas never substitute future prices"
        )

        unknown = await call(
            "unknown",
            "market_decision_record",
            {
                "account_id": connection,
                "symbol": "NOT_A_BROKER_SYMBOL",
                "timeframe": "1h",
                "action": "SELL",
                "summary": "No invented quote for unknown market",
            },
        )
        assert unknown["action"] == "SELL" and unknown["gate_codes"]
        assert unknown["readiness"]["execution_readiness"]["state"] == "BLOCKED"
        try:
            async with f.runtime.db.sessions() as session:
                await read_decision(session, uuid4().hex, records[0]["id"])
        except LonoraError as error:
            assert error.code == "decision_not_found"
        else:
            raise AssertionError("Decision leaked across owners")
        phase = 0

        async def complete(
            capability: Any, messages: list[ModelMessage], tools: Any, **kwargs: Any
        ):
            nonlocal phase
            phase += 1
            if phase == 1:
                assert "recorded_decisions" in messages[0].content
                reply = ModelReply(
                    tool_calls=[
                        ToolCall(
                            id="runtime-decision",
                            name="market_decision_record",
                            arguments={
                                "account_id": connection,
                                "symbol": symbols[0],
                                "timeframe": frames[0],
                                "action": "BUY",
                                "summary": "Public fixture reason; backend freshness is authoritative",
                            },
                        )
                    ]
                )
            else:
                observation = next(
                    message
                    for message in messages
                    if message.role == "tool" and message.tool_call_id == "runtime-decision"
                )
                persisted = json.loads(observation.content)
                assert persisted["action"] == "BUY" and persisted["ok"] is True
                assert persisted["readiness"]["execution_readiness"]["state"] == "BLOCKED"
                reply = ModelReply(text="WAIT: stored source data is stale")
            return reply, ModelSelection(provider="openai", model="scripted-decision-fixture")

        with patch.object(context.router, "complete", complete):
            await execute_run(context, registry, 120, 4)
        async with f.runtime.db.sessions() as session:
            run = await session.get(RunRow, context.lease.run_id)
            assert (
                run
                and run.status == "completed"
                and run.result == "WAIT: stored source data is stale"
            )
        print(
            "PASS same AgentRuntime/global routing/tool loop persists gated decision and returns confirmed runtime truth to chat"
        )

        specialist = await f.agent("Exact scope replay")
        async with f.runtime.db.sessions() as session, session.begin():
            row = await session.get(AgentRow, specialist["id"])
            assert row
            row.role = "specialist"
            row.trading_account_id = connection
            row.trading_symbol = symbols[0]
        specialist_thread = await f.conversation(specialist)
        specialist_context = await f.lease(await f.run(specialist, specialist_thread))
        try:
            await registry.execute(
                ToolCall(
                    id="scope-check",
                    name="market_decision_read",
                    arguments={"decision_id": records[1]["id"]},
                ),
                specialist_context,
            )
        except LonoraError as error:
            assert error.code == "agent_trading_symbol_mismatch"
        else:
            raise AssertionError("Specialist read an unbound market decision")
        api = await f.request("GET", f"/trading/decisions/{records[0]['id']}")
        assert api["evidence"]["quote"]["bid"] == "100"
        await f.client.delete(f"/api/trading/connections/{connection}")
        connection = ""
        retained = await f.request("GET", f"/trading/decisions/{records[0]['id']}")
        assert retained == api
        print(
            "PASS missing market blocks execution without rewriting model intent; owner isolation and API replay survive fresh sessions"
        )
    finally:
        if connection:
            await f.client.delete(f"/api/trading/connections/{connection}")
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
