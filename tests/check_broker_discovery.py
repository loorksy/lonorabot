"""Actual API/PG broker-ID discovery; explicitly imported simulation, no live trades."""

import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_adapters.brokers.metaapi import MetaApiBroker
from lonora_core.user_error import LonoraError
from lonora_db.schema import TradingAccountRow
from lonora_tools.loader import load_tools


async def main() -> None:
    fixture = await Fixture().open()
    connection_id = None
    try:
        agent = await fixture.agent("Broker discovery fixture")
        thread = await fixture.conversation(agent)
        context = await fixture.lease(await fixture.run(agent, thread))
        external_id = "external-metaapi-style-" + uuid4().hex
        connection = await fixture.request(
            "POST",
            "/trading/connections",
            {
                "provider": "simulation",
                "account_id": external_id,
                "enabled": True,
            },
        )
        connection_id = connection["id"]
        await fixture.request(
            "POST",
            f"/trading/connections/{connection_id}/simulation",
            {
                "snapshot": {
                    "balance": "1234.50",
                    "currency": "USD",
                    "instruments": [
                        {
                            "symbol": "XAUUSD.a",
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.01",
                            "volume_max": "100",
                            "volume_step": "0.01",
                        }
                    ],
                    "quotes": {
                        "XAUUSD.a": {
                            "symbol": "XAUUSD.a",
                            "bid": "4000",
                            "ask": "4001",
                            "observed_at": "2026-10-13T14:00:00Z",
                            "source": "explicit-test-snapshot",
                        }
                    },
                    "candles": {
                        "XAUUSD.a:15m": [
                            {
                                "symbol": "XAUUSD.a",
                                "timeframe": "15m",
                                "time": "2026-10-13T13:30:00Z",
                                "open": "4000",
                                "high": "4005",
                                "low": "3998",
                                "close": "4003",
                            },
                            {
                                "symbol": "XAUUSD.a",
                                "timeframe": "15m",
                                "time": "2026-10-13T13:45:00Z",
                                "open": "4003",
                                "high": "4006",
                                "low": "4000",
                                "close": "4001",
                            },
                        ]
                    },
                },
            },
        )
        registry = load_tools()
        directory = await registry.execute(
            ToolCall(id="list", name="list_accounts", arguments={}), context, read_only=True
        )
        row = next(item for item in directory["accounts"] if item["connection_id"] == connection_id)
        assert row["broker_account_id"] == external_id
        assert "secret_id" not in row and "api_key" not in row
        try:
            await registry.execute(
                ToolCall(id="wrong", name="account_read", arguments={"account_id": external_id}),
                context,
                read_only=True,
            )
            raise AssertionError("External ID unexpectedly accepted")
        except LonoraError as error:
            assert error.code == "broker_sessions_not_found"
        actual = await registry.execute(
            ToolCall(
                id="actual", name="account_read", arguments={"account_id": row["connection_id"]}
            ),
            context,
            read_only=True,
        )
        assert "1234.50" in str(actual) and "USD" in str(actual), actual
        print(
            "PASS saved account discovery uses the internal connection ID and reads actual imported balance without exposing secrets"
        )

        async def sdk_spec(symbol: str):
            if symbol != "XAUUSD.a":
                raise RuntimeError("Explicit fixture: unrelated symbol specifications unavailable")
            return {
                "symbol": symbol,
                "digits": 2,
                "tickSize": 0.01,
                "minVolume": 0.01,
                "maxVolume": 100,
                "volumeStep": 0.01,
            }

        rpc = SimpleNamespace(
            get_symbols=AsyncMock(return_value=["BROKEN", "XAUUSD.a"]),
            get_symbol_specification=AsyncMock(side_effect=sdk_spec),
        )
        sdk_broker = object.__new__(MetaApiBroker)
        with patch.object(MetaApiBroker, "prepare", AsyncMock(return_value=rpc)):
            assert await sdk_broker.symbols() == ["BROKEN", "XAUUSD.a"]
            rpc.get_symbol_specification.assert_not_awaited()
            assert (await sdk_broker.instrument("XAUUSD.a")).symbol == "XAUUSD.a"
            rpc.get_symbol_specification.assert_awaited_once_with("XAUUSD.a")
        print("PASS MetaApi targeted lookup avoids unrelated specification failures (scripted SDK)")
        symbols = await registry.execute(
            ToolCall(id="symbols", name="market_symbols", arguments={"account_id": connection_id}),
            context,
            read_only=True,
        )
        assert symbols["symbols"] == ["XAUUSD.a"]
        base = {"account_id": connection_id, "symbol": "XAUUSD.a"}
        spec = await registry.execute(
            ToolCall(id="spec", name="market_instrument", arguments=base), context, read_only=True
        )
        assert spec["symbol"] == "XAUUSD.a" and spec["tick_size"] == "0.01"
        quote = await registry.execute(
            ToolCall(id="quote", name="market_quote", arguments=base), context, read_only=True
        )
        assert quote["source"] == "explicit-test-snapshot" and quote["bid"] == "4000"
        candles = await registry.execute(
            ToolCall(id="candles", name="market_candles", arguments={**base, "timeframe": "15m"}),
            context,
            read_only=True,
        )
        assert len(candles["candles"]) == 2
        artifact = await registry.execute(
            ToolCall(id="chart", name="chart_snapshot", arguments={**base, "timeframe": "15m"}),
            context,
        )
        assert artifact["payload"]["media_type"] == "image/svg+xml"
        image = context.artifact_root / artifact["payload"]["key"]
        assert "XAUUSD.a" in image.read_text() and "polyline" in image.read_text()
        image.unlink()
        print(
            "PASS exact suffixed gold symbol, targeted specifications, sourced quote, candles and persisted chart image"
        )
    finally:
        if connection_id:
            async with fixture.runtime.db.sessions() as session, session.begin():
                row = await session.get(TradingAccountRow, connection_id)
                if row:
                    await session.delete(row)
            await fixture.request("DELETE", f"/trading/connections/{connection_id}")
        await fixture.close()


if __name__ == "__main__":
    asyncio.run(main())
