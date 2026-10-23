"""Real registry/PG/simulation structure evidence and existing chart integration."""

import asyncio
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.domain import utcnow
from lonora_core.user_error import LonoraError
from lonora_db.schema import MarketSnapshotRow, TradingAccountRow, TradingJournalRow
from lonora_tools.context import ToolContext
from lonora_tools.loader import load_tools
from sqlalchemy import delete, func, select


async def main() -> None:
    fixture = await Fixture().open()
    connection_id: str | None = None
    chart_id: str | None = None
    try:
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
        )
        connection_id = str(connection["id"])
        now = utcnow()
        definitions = [
            ("EURUSDm", Decimal("1.10000"), Decimal("0.00001"), 5),
            ("XAUUSD.pro", Decimal("2700"), Decimal("0.01"), 2),
            ("US500.cash", Decimal("5600"), Decimal("0.1"), 1),
            ("BTCUSD.a", Decimal("65000"), Decimal("0.01"), 2),
        ]
        symbols = [item[0] for item in definitions]
        candles: dict[str, list[dict[str, Any]]] = {}
        wave = [0, 2, 4, 2, 0, -2, -4, -2]
        for frame, minutes in (("1m", 1), ("15m", 15)):
            floor = now.replace(second=0, microsecond=0)
            floor -= timedelta(minutes=floor.minute % minutes)
            for symbol, base, tick, _ in definitions:
                bars: list[dict[str, Any]] = []
                for index in range(50):
                    price = base + tick * (Decimal(index) + Decimal(wave[index % 8] * 10))
                    bars.append(
                        {
                            "symbol": symbol,
                            "timeframe": frame,
                            "time": (floor - timedelta(minutes=(49 - index) * minutes)).isoformat(),
                            "open": str(price),
                            "high": str(price + tick * 2),
                            "low": str(price - tick * 2),
                            "close": str(price + tick),
                        }
                    )
                candles[symbol + ":" + frame] = bars
        await fixture.request(
            "POST",
            f"/trading/connections/{connection_id}/simulation",
            {
                "snapshot": {
                    "balance": "10000",
                    "currency": "USD",
                    "instruments": [
                        {
                            "symbol": symbol,
                            "digits": digits,
                            "tick_size": str(tick),
                            "volume_min": "0.01",
                            "volume_max": "10",
                            "volume_step": "0.01",
                        }
                        for symbol, _, tick, digits in definitions
                    ],
                    "quotes": {
                        symbol: {
                            "symbol": symbol,
                            "bid": str(base),
                            "ask": str(base + tick),
                            "observed_at": now.isoformat(),
                            "source": "explicit-structure-fixture",
                        }
                        for symbol, base, tick, _ in definitions
                    },
                    "candles": candles,
                }
            },
        )
        agent = await fixture.agent("Market structure analyst")
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        registry = load_tools()
        tool = registry.tools["market_structure"]
        assert tool.read_only and not tool.financial
        assert "market_structure" in {item.name for item in registry.definitions(read_only=True)}

        async def call(
            name: str, args: dict[str, Any], *, actor: ToolContext = context
        ) -> dict[str, Any]:
            return await registry.execute(
                ToolCall(id=uuid4().hex, name=name, arguments=args), actor
            )

        async def denied(
            name: str, args: dict[str, Any], code: str, *, actor: ToolContext = context
        ) -> None:
            try:
                await call(name, args, actor=actor)
            except LonoraError as error:
                assert error.code == code, (name, error.code, code)
            else:
                raise AssertionError(name + " accepted invalid evidence or scope")

        requests = [
            {"account_id": connection_id, "symbol": symbol, "timeframe": frame}
            for frame in ("1m", "15m")
            for symbol in symbols
        ]
        results = await asyncio.gather(*(call("market_structure", args) for args in requests))
        for args, result in zip(requests, results, strict=True):
            assert result["symbol"] == args["symbol"] and result["timeframe"] == args["timeframe"]
            assert result["health"]["state"] == "healthy"
            assert result["execution_authorized"] is False
            assert result["pivots"] and result["trendlines"]
            assert result["input"]["closed_bars"] == 49
            assert result["input"]["excluded_forming_bars"] == 1
            for observation in result["pivots"] + result["trendlines"]:
                assert observation["symbol"] == args["symbol"]
                assert observation["timeframe"] == args["timeframe"]
                assert observation["values"]["execution_authorized"] is False
                assert observation["values"]["source_hash"]
        measured = results[0]
        print(
            "PASS real registry: concurrent forex/metal/index/crypto exact suffixes and two frames; closed-bar evidence, alternative lines and zero execution authority"
        )

        bound = await fixture.request(
            "POST",
            "/agents",
            {
                "name": "Bound structure fixture",
                "trading_account_id": connection_id,
                "trading_symbol": symbols[0],
            },
        )
        fixture.agents.append(bound["id"])
        bound_context = await fixture.lease(
            await fixture.run(bound, await fixture.conversation(bound))
        )
        restored = await call("market_structure", {"timeframe": "1m"}, actor=bound_context)
        assert restored["symbol"] == symbols[0]
        await denied(
            "market_structure",
            {"account_id": connection_id, "symbol": symbols[1], "timeframe": "1m"},
            "agent_trading_symbol_mismatch",
            actor=bound_context,
        )
        await denied(
            "market_structure",
            {"account_id": connection_id, "symbol": "UNKNOWN.suffix", "timeframe": "1m"},
            "symbol_not_found",
        )
        await denied(
            "market_structure",
            {"account_id": connection_id, "symbol": symbols[0], "timeframe": "H1"},
            "unsupported_timeframe",
        )
        print(
            "PASS immutable specialist defaults and scope denial; unknown symbol/timeframe remain precise errors"
        )

        # A working quote must not turn a history failure into fabricated evidence.
        live_quote = await call("market_quote", {"account_id": connection_id, "symbol": symbols[0]})
        assert live_quote["symbol"] == symbols[0]
        broker = await context.brokers.get(context.owner_id, connection_id)
        async with context.db.sessions() as session, session.begin():
            await session.execute(
                delete(MarketSnapshotRow).where(
                    MarketSnapshotRow.connection_id == connection_id,
                    MarketSnapshotRow.timeframe == "1m",
                )
            )
        failed_history = AsyncMock(side_effect=LonoraError("broker_candles_unavailable", 409))
        with patch.object(broker, "candles", failed_history):
            await denied("market_structure", requests[0], "broker_candles_unavailable")
        assert failed_history.await_count == 1
        after_failure = await call("market_structure", requests[0])
        assert after_failure["source_hash"] == measured["source_hash"]
        print(
            "PASS connected quote/history failure propagates without fake structure and recovers on next actual read"
        )

        # The broker corrects an old completed bar. Preserve the old returned proof,
        # but expire the ordinary runtime cache before explicitly rereading it.
        original = deepcopy(measured)
        async with context.db.sessions() as session, session.begin():
            row = await session.get(TradingAccountRow, connection_id, with_for_update=True)
            assert row
            payload = deepcopy(row.payload)
            corrected = payload["candles"][symbols[0] + ":1m"][18]
            corrected["high"] = str(Decimal(corrected["high"]) + Decimal("0.001"))
            row.payload = payload
            await session.execute(
                delete(MarketSnapshotRow).where(
                    MarketSnapshotRow.connection_id == connection_id,
                    MarketSnapshotRow.symbol == symbols[0],
                    MarketSnapshotRow.timeframe == "1m",
                )
            )
        corrected_result = await call("market_structure", requests[0])
        assert corrected_result["source_hash"] != original["source_hash"]
        assert measured == original
        assert corrected_result["pivots"] != original["pivots"]
        print(
            "PASS corrected closed OHLC creates a new proof without rewriting returned historical evidence"
        )

        # Consume real measured anchors using the existing drawing mutation and
        # scene inspection paths; the analyzer does not draw or grant permission.
        line = measured["trendlines"][0]
        anchors = line["values"]["anchors"]
        created = await call(
            "chart_open",
            {"account_id": connection_id, "symbol": symbols[0], "timeframe": "1m"},
        )
        chart_id = created["chart"]["id"]
        version = created["chart"]["version"]
        annotation_id = "measured-structure-line"
        annotated = await call(
            "chart_annotate",
            {
                "chart_id": chart_id,
                "version": version,
                "annotation": {
                    "id": annotation_id,
                    "type": "trend_line",
                    "start": anchors[0],
                    "end": anchors[1],
                    "label": line["values"]["role"],
                },
            },
        )
        assert annotated["requires_scene_inspection"] and annotated["scene"] is None
        inspected = await call("chart_inspect", {"chart_id": chart_id})
        drawing = next(
            item for item in inspected["scene"]["annotations"] if item["id"] == annotation_id
        )
        assert drawing["start"] == anchors[0] and drawing["end"] == anchors[1]
        assert drawing["source"] == "agent" and drawing["author_id"] == agent["id"]
        await denied(
            "chart_annotate",
            {
                "chart_id": chart_id,
                "version": version,
                "operations": [{"op": "delete", "id": annotation_id}],
            },
            "version_conflict",
        )
        await denied(
            "chart_annotate",
            {
                "chart_id": chart_id,
                "version": inspected["chart"]["version"],
                "operations": [{"op": "delete", "id": annotation_id}],
            },
            "chart_annotation_forbidden",
            actor=bound_context,
        )
        final = await call("chart_inspect", {"chart_id": chart_id, "include_scene": False})
        assert (
            final["chart"]["payload"]["annotations"] == inspected["chart"]["payload"]["annotations"]
        )
        async with context.db.sessions() as session:
            assert await session.scalar(select(func.count()).select_from(TradingJournalRow)) == 0
        assert not await broker.positions() and not await broker.orders()
        print(
            "PASS measured anchors → attributed drawing → actual scene inspection; stale revision and peer deletion denied; no journal or broker mutation"
        )
    finally:
        if chart_id:
            await fixture.request("DELETE", "/charts/" + chart_id)
        if connection_id:
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(TradingAccountRow, connection_id)
                if row:
                    await session.delete(row)
            await fixture.request("DELETE", "/trading/connections/" + connection_id)
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
