"""Shadow commands and background protection never call the real broker executor."""

import asyncio
from datetime import timedelta
from decimal import Decimal
from typing import Any
from unittest.mock import AsyncMock, patch
from uuid import uuid4

from check_streaming import Fixture
from lonora_adapter_kit.types import ToolCall
from lonora_contracts.domain import utcnow
from lonora_contracts.trading import TradeRequest
from lonora_core.user_error import LonoraError
from lonora_db.schema import TradingAccountRow
from lonora_db.trading_journal import journal_entries
from lonora_tools.loader import load_tools
from lonora_trading.shadow import advance_shadow


async def main():
    f = await Fixture().open()
    try:
        account = (
            await f.request(
                "POST",
                "/trading/connections",
                {"provider": "simulation", "account_id": uuid4().hex, "enabled": True},
            )
        )["id"]
        symbols = ("EURUSDm", "XAUUSDm", "US30.cash", "BTCUSD.pro")
        now = utcnow()
        await f.request(
            "POST",
            f"/trading/connections/{account}/simulation",
            {
                "snapshot": {
                    "balance": "10000",
                    "currency": "USD",
                    "instruments": [
                        {
                            "symbol": s,
                            "digits": 2,
                            "tick_size": "0.01",
                            "volume_min": "0.01",
                            "volume_max": "10",
                            "volume_step": "0.01",
                        }
                        for s in symbols
                    ],
                    "quotes": {
                        s: {
                            "symbol": s,
                            "bid": "100",
                            "ask": "101",
                            "observed_at": now.isoformat(),
                            "source": "explicit-shadow-fixture",
                        }
                        for s in symbols
                    },
                    "candles": {
                        s + ":1m": [
                            {
                                "symbol": s,
                                "timeframe": "1m",
                                "time": (now - timedelta(seconds=60)).isoformat(),
                                "open": "100",
                                "high": "103",
                                "low": "99",
                                "close": "101",
                            }
                        ]
                        for s in symbols
                    },
                }
            },
        )
        agent = await f.agent("Shadow researcher")
        mode = await f.request(
            "PUT", f"/agents/{agent['id']}/execution-mode", {"execution_mode": "shadow"}
        )
        assert mode["execution_mode"] == "shadow"
        thread = await f.conversation(agent)
        context = await f.lease(await f.run(agent, thread))
        registry = load_tools()
        broker = await context.brokers.get(f.owner, account)
        trap = AsyncMock(side_effect=AssertionError("Shadow must never call live broker.execute"))

        async def tool(name: str, args: dict[str, Any], key: str | None = None):
            return await registry.execute(
                ToolCall(id=key or uuid4().hex, name=name, arguments=args), context
            )

        async def record(symbol: str, direction: str):
            return await tool(
                "market_decision_record",
                {
                    "account_id": account,
                    "symbol": symbol,
                    "timeframe": "1m",
                    "action": direction,
                    "summary": "Recorded public virtual-analysis fixture",
                },
            )

        with patch.object(broker, "execute", trap):
            ids: list[str] = []
            for symbol in symbols:
                await record(symbol, "BUY")
                args = {
                    "account_id": account,
                    "symbol": symbol,
                    "action": "buy",
                    "volume": "0.1",
                    "stop_loss": "90",
                    "take_profit": "120",
                }
                virtual = await tool("trade_execute", args, symbol)
                assert virtual["details"]["mode"] == "shadow" and virtual["status"] == "confirmed"
                replay = await tool("trade_execute", args, symbol)
                assert replay["operation_id"] == virtual["operation_id"]
                ids.append(virtual["broker_id"])
            assert await broker.positions() == [] and trap.await_count == 0
            await tool(
                "trade_execute",
                {
                    "account_id": account,
                    "symbol": symbols[0],
                    "action": "modify_position",
                    "position_id": ids[0],
                    "stop_loss": "91",
                },
            )
            await tool(
                "trade_execute",
                {
                    "account_id": account,
                    "symbol": symbols[0],
                    "action": "close_position",
                    "position_id": ids[0],
                    "volume": "0.04",
                },
            )
            view = await tool("market_shadow_read", {"account_id": account})
            first = next(row for row in view["trades"] if row["id"] == ids[0])
            assert first["state"]["remaining_volume"] == "0.06" and first["monetary_pnl"] is None
            assert set(first["state"]["quality"]) == {
                "analysis",
                "entry",
                "management",
                "execution",
            }
            print(
                "PASS four exact asset classes, idempotent virtual entry, partial close/protection and separate quality evidence; real broker mutations zero"
            )

            await record(symbols[1], "SELL")
            for kind, price in (
                ("buy_limit", "95"),
                ("buy_stop", "110"),
                ("sell_limit", "110"),
                ("sell_stop", "95"),
            ):
                await record(symbols[1], "BUY" if kind.startswith("buy") else "SELL")
                pending = await tool(
                    "trade_execute",
                    {
                        "account_id": account,
                        "symbol": symbols[1],
                        "action": kind,
                        "volume": "0.1",
                        "price": price,
                    },
                )
                await tool(
                    "trade_execute",
                    {
                        "account_id": account,
                        "symbol": symbols[1],
                        "action": "modify_order",
                        "order_id": pending["broker_id"],
                        "price": "94" if kind in {"buy_limit", "sell_stop"} else "111",
                    },
                )
                with patch.object(
                    context.brokers,
                    "get",
                    AsyncMock(side_effect=LonoraError("broker_connection_unavailable", 409)),
                ):
                    cancelled = await tool(
                        "trade_execute",
                        {
                            "account_id": account,
                            "symbol": symbols[1],
                            "action": "cancel_order",
                            "order_id": pending["broker_id"],
                        },
                    )
                assert cancelled["details"]["virtual_status"] == "cancelled"
            assert await broker.orders() == []
            print(
                "PASS all four pending types, modify and cancel are persistent virtual operations only"
            )

            await record(symbols[1], "BUY")
            crossing = await tool(
                "trade_execute",
                {
                    "account_id": account,
                    "symbol": symbols[1],
                    "action": "buy_stop",
                    "volume": "0.1",
                    "price": "110",
                    "stop_loss": "90",
                },
            )

            async with f.runtime.db.sessions() as session, session.begin():
                row = await session.get(TradingAccountRow, account, with_for_update=True)
                assert row
                quotes = dict(row.payload["quotes"])
                quotes[symbols[0]] = {
                    **quotes[symbols[0]],
                    "bid": "121",
                    "ask": "122",
                    "observed_at": utcnow().isoformat(),
                }
                quotes[symbols[1]] = {
                    **quotes[symbols[1]],
                    "bid": "110",
                    "ask": "111",
                    "observed_at": utcnow().isoformat(),
                }
                quotes[symbols[2]] = {
                    **quotes[symbols[2]],
                    "bid": "89",
                    "ask": "90",
                    "observed_at": utcnow().isoformat(),
                }
                row.payload = {**row.payload, "quotes": quotes}
            assert await advance_shadow(f.runtime.db, context.brokers, f.owner) >= 1
            assert await advance_shadow(f.runtime.db, context.brokers, f.owner) == 0
            view = await tool("market_shadow_read", {"account_id": account})
            first = next(row for row in view["trades"] if row["id"] == ids[0])
            assert first["status"] == "closed" and first["state"]["exit_reason"] == "virtual_target"
            assert first["payload"]["fill_model"] == "sampled_top_of_book_no_depth"
            assert first["monetary_pnl"] is None
            expected_return = (Decimal("-1") / Decimal("101")) * Decimal("0.4") + (
                Decimal("20") / Decimal("101")
            ) * Decimal("0.6")
            assert abs(
                Decimal(first["state"]["price_return_fraction"]) - expected_return
            ) < Decimal("1e-25")
            assert Decimal(first["state"]["closed_volume"]) == Decimal("0.1")
            filled = next(row for row in view["trades"] if row["id"] == crossing["broker_id"])
            assert filled["status"] == "open" and filled["state"]["entry_price"] == "111"
            assert filled["state"]["entry_quote"]["ask"] == "111"
            stopped = next(row for row in view["trades"] if row["id"] == ids[2])
            assert (
                stopped["status"] == "closed" and stopped["state"]["exit_reason"] == "virtual_stop"
            )
            performance = await tool(
                "market_performance_read", {"execution_mode": "shadow", "account_id": account}
            )
            assert (
                performance["sample_state"] == "insufficient_data"
                and not performance["live_authority_granted"]
            )
            async with f.runtime.db.sessions() as session:
                assert await journal_entries(session, f.owner, account) == []
                shadow = await journal_entries(session, f.owner, account, execution_mode="shadow")
                assert shadow and all(entry.execution_mode == "shadow" for entry in shadow)
            print(
                "PASS background sampled quote target/restart dedup, virtual history, explicit granularity and live/shadow journal/performance separation"
            )
            api_history = await f.request("GET", f"/agents/{agent['id']}/shadow-trades")
            assert api_history["mode"] == "shadow" and len(api_history["trades"]) == 9
            api_performance = await f.request(
                "GET", f"/agents/{agent['id']}/performance?execution_mode=shadow"
            )
            assert api_performance["sample_count"] == 2
            live_performance = await f.request(
                "GET", f"/agents/{agent['id']}/performance?execution_mode=live"
            )
            assert live_performance["sample_count"] == 0
            missing = await f.client.get(f"/api/agents/{uuid4()}/shadow-trades")
            assert missing.status_code == 404
            explicit = await f.client.get(f"/api/agents/{agent['id']}/performance")
            assert explicit.status_code == 422
            closed_all = await tool("trade_close_positions", {"account_id": account}, "close-all")
            assert len(closed_all["results"]) == 3
            replay_all = await tool("trade_close_positions", {"account_id": account}, "close-all")
            assert replay_all == closed_all
            assert trap.await_count == 0
            await f.request(
                "PUT", f"/agents/{agent['id']}/execution-mode", {"execution_mode": "live"}
            )
            try:
                await context.trading.execute(
                    f.owner,
                    TradeRequest(
                        account_id=account,
                        operation_id=uuid4().hex,
                        symbol=symbols[0],
                        action="buy",
                        volume=Decimal("0.1"),
                    ),
                    context.lease,
                )
            except LonoraError as error:
                assert error.code == "shadow_execution_forbidden"
            else:
                raise AssertionError(
                    "Switching mode widened an existing shadow Run's financial authority"
                )
            assert trap.await_count == 0
            controls = await f.request("GET", "/trading/controls")
            assert controls["enabled"] is False
            print(
                "PASS mode change never widens existing Run authority or enables global live trading"
            )
    finally:
        await f.close()


if __name__ == "__main__":
    asyncio.run(main())
