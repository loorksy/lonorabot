"""Actual AgentToolLoop/PostgreSQL/attachment research with imported simulation data."""

import asyncio
import json
from datetime import timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from typing import Any
from unittest.mock import patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ModelMessage, ModelReply, ToolCall
from lonora_agent.executor import execute_run
from lonora_contracts.domain import utcnow
from lonora_contracts.model_routing import Capability, ModelSelection
from lonora_core.user_error import LonoraError
from lonora_db.schema import AgentRow, ArtifactRow, MessageRow, TradingAccountRow, TradingJournalRow
from lonora_market.research import ResearchResult, digest
from lonora_security.runtime_storage import confined_path
from lonora_tools.loader import load_tools
from sqlalchemy import func, select


async def main() -> None:
    fixture = await Fixture().open()
    original_root = fixture.settings.artifact_root
    connection_id: str | None = None
    with TemporaryDirectory(prefix="lonora-research-") as directory:
        try:
            fixture.settings.artifact_root = Path(directory)
            symbol = "INDEX.cash"
            connection = await fixture.request(
                "POST",
                "/trading/connections",
                {
                    "provider": "simulation",
                    "account_id": "research-" + uuid4().hex,
                    "enabled": True,
                },
            )
            connection_id = connection["id"]
            now = utcnow().replace(second=0, microsecond=0)
            bars = [
                {
                    "symbol": symbol,
                    "timeframe": "1m",
                    "time": (now - timedelta(minutes=100 - index)).isoformat(),
                    "open": str(100 + index),
                    "high": str(102 + index),
                    "low": str(99 + index),
                    "close": str(101 + index),
                }
                for index in range(101)
            ]
            await fixture.request(
                "POST",
                f"/trading/connections/{connection_id}/simulation",
                {
                    "snapshot": {
                        "currency": "USD",
                        "balance": "10000",
                        "positions": [],
                        "orders": [],
                        "instruments": [
                            {
                                "symbol": symbol,
                                "digits": 1,
                                "tick_size": "0.1",
                                "volume_min": "0.1",
                                "volume_max": "10",
                                "volume_step": "0.1",
                            }
                        ],
                        "candles": {symbol + ":1m": bars},
                    },
                },
            )
            agent = await fixture.agent("Strategy research")
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(AgentRow, agent["id"])
                assert row
                row.trading_account_id, row.trading_symbol = connection_id, symbol
            thread = await fixture.conversation(agent)
            context = await fixture.lease(await fixture.run(agent, thread))
            registry = load_tools()
            assert registry.tools["market_strategy_research"].read_only
            arguments: dict[str, Any] = {
                "timeframe": "1m",
                "limit": 120,
                "config": {
                    "candidates": [{"fast": 2, "slow": 5}, {"fast": 3, "slow": 8}],
                    "gap_policy": "reject",
                    "seed": 123,
                    "monte_carlo_samples": 20,
                    "scenario": {
                        "currency": "USD",
                        "initial_equity": "10000",
                        "volume": "0.1",
                        "tick_value_per_lot": "1",
                        "price_basis": "bid",
                        "spread_ticks": "2",
                        "slippage_ticks_per_side": "1",
                        "commission_per_lot_side": "1",
                        "carry_cost_per_lot_day": "0",
                        "latency_bars": 1,
                        "provenance": "Explicit analytical scenario for a disposable simulation fixture.",
                    },
                },
            }
            async with context.db.sessions() as session:
                journal_before = await session.scalar(
                    select(func.count()).select_from(TradingJournalRow)
                )
            rounds = 0
            report_id = ""

            async def model(
                _capability: Capability, messages: list[ModelMessage], _tools: Any, **_kwargs: Any
            ):
                nonlocal rounds, report_id
                rounds += 1
                if rounds == 1:
                    reply = ModelReply(
                        tool_calls=[
                            ToolCall(
                                id="historical-analysis",
                                name="market_strategy_research",
                                arguments=arguments,
                            )
                        ]
                    )
                else:
                    observation = next(
                        message
                        for message in messages
                        if message.role == "tool" and message.tool_call_id == "historical-analysis"
                    )
                    result = json.loads(observation.content)
                    assert (
                        result["mode"] == "historical_research"
                        and not result["execution_authorized"]
                    )
                    assert result["symbol"] == symbol and result["bars"] == 100
                    assert result["excluded_incomplete_bars"] == 1
                    assert (
                        result["out_of_sample"] and result["economics"] == "declared_scenario_only"
                    )
                    report_id = result["artifact_id"]
                    reply = ModelReply(
                        text="The historical scenario analysis is attached. It does not authorize a trade."
                    )
                return reply, ModelSelection(provider="openai", model="scripted-research-fixture")

            with patch.object(context.router, "complete", model):
                await execute_run(context, registry, 120, 5)
            assert rounds == 2 and report_id
            async with context.db.sessions() as session:
                report = await session.get(ArtifactRow, report_id)
                assert report and report.state["research_scope"]["symbol"] == symbol
                delivered = await session.scalar(
                    select(MessageRow)
                    .where(
                        MessageRow.thread_id == context.thread_id,
                        MessageRow.role == "assistant",
                    )
                    .order_by(MessageRow.seq.desc())
                    .limit(1)
                )
                assert delivered and delivered.attachment_ids == [report_id]
                assert report.state["delivered_message_id"] == delivered.id
                assert (
                    await session.scalar(select(func.count()).select_from(TradingJournalRow))
                    == journal_before
                )
                account = await session.get(TradingAccountRow, connection_id)
                assert (
                    account
                    and not account.payload.get("positions")
                    and not account.payload.get("orders")
                )
                assert not account.payload.get("operations")
                report_key = report.payload["key"]
                original = dict(report.state["research_summary"])
            download = await fixture.client.get("/api/artifacts/" + report_id + "/file")
            assert download.status_code == 200
            result = ResearchResult.model_validate_json(download.content)
            assert result.result_sha256 == digest(
                result.model_dump(mode="json", exclude={"result_sha256"})
            )
            assert len(result.dataset) == 100 and result.instrument.symbol == symbol

            # Re-lease the completed fixture only to exercise the original call's
            # immutable receipt independently from AgentToolLoop checkpoints.
            context = await fixture.lease(
                {
                    "id": context.lease.run_id,
                    "agent_id": context.agent_id,
                    "thread_id": context.thread_id,
                }
            )
            assert connection_id is not None
            broker = await context.brokers.get(context.owner_id, connection_id)
            with patch.object(
                broker,
                "candles",
                side_effect=AssertionError("Receipt replay queried mutable history"),
            ):
                replay = await registry.execute(
                    ToolCall(
                        id="historical-analysis",
                        name="market_strategy_research",
                        arguments=arguments,
                    ),
                    context,
                )
                assert replay == original
            history = await registry.execute(
                ToolCall(id="find-history", name="market_research_history", arguments={}), context
            )
            assert history["reports"][0]["artifact_id"] == report_id
            try:
                await registry.execute(
                    ToolCall(
                        id="wrong-scope",
                        name="market_strategy_research",
                        arguments={**arguments, "symbol": "WRONG"},
                    ),
                    context,
                )
            except LonoraError as error:
                assert error.code == "agent_trading_symbol_mismatch"
            else:
                raise AssertionError("Cross-symbol research escaped immutable Agent binding")
            try:
                await registry.execute(
                    ToolCall(
                        id="historical-analysis",
                        name="market_strategy_research",
                        arguments={**arguments, "limit": 100},
                    ),
                    context,
                )
            except LonoraError as error:
                assert error.code == "research_receipt_conflict"
            else:
                raise AssertionError("Changed request reused original report identity")
            path = confined_path(context.artifact_root, report_key)
            original_content = path.read_bytes()
            path.write_bytes(b"corrupted")
            try:
                await registry.execute(
                    ToolCall(
                        id="historical-analysis",
                        name="market_strategy_research",
                        arguments=arguments,
                    ),
                    context,
                )
            except LonoraError as error:
                assert error.code == "artifact_integrity_failed"
            else:
                raise AssertionError("Corrupt analytical report was trusted")
            path.write_bytes(original_content)
            print(
                "PASS ordinary AgentToolLoop -> canonical simulation history/specification -> reproducible research -> PG artifact -> chat attachment/download; incomplete bars excluded, immutable replay, exact scope, history retrieval, corruption and zero financial effects"
            )
        finally:
            fixture.settings.artifact_root = original_root
            if connection_id:
                await fixture.request("DELETE", "/trading/connections/" + connection_id)
            await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
